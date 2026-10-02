"""Independent-review M9 regressions; isolated DB, synthetic providers only."""

from __future__ import annotations

import copy
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import test_m9_experiments as m9
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from sports_intelligence.api.app import create_app
from sports_intelligence.bot.backend_client import BackendClient
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.experiments import experiment_callback
from sports_intelligence.db.models import (
    Experiment,
    ExperimentArm,
    ExperimentRun,
    ExternalApiRequest,
    Fixture,
    ImprovementProposal,
    ImprovementProposalEvent,
    League,
    Team,
)
from sports_intelligence.experiments.analyst import approve_experiment
from sports_intelligence.experiments.contracts import (
    ApproveRequest,
    ArmRequest,
    ExperimentDefinition,
    RunRequest,
)
from sports_intelligence.experiments.planner import plan_replay
from sports_intelligence.experiments.service import request_run
from sports_intelligence.predictions.identity import fingerprint
from telegram_fakes import FakeTransport, make_callback

factory = m9.factory
record = m9.record
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="test DB required"),
]
COMPONENTS = ("prompt", "model", "data_quality", "features", "ranking", "sources")


async def missing_fixture(factory, record):
    async with factory() as s, s.begin():
        original = await s.get(Fixture, record.fixture_id)
        row = Fixture(
            league_id=original.league_id,
            home_team_id=original.home_team_id,
            away_team_id=original.away_team_id,
            kickoff_at=record.as_of + timedelta(hours=7),
            status="NS",
        )
        s.add(row)
        await s.flush()
        return row


@pytest.mark.parametrize("league_filter", [False, True])
async def test_broad_historical_population_invariant_under_mutable_fixture_changes(
    factory, record, league_filter
):
    missing = await missing_fixture(factory, record)
    data = m9.definition(record).model_dump(mode="json")
    data["population"]["fixture_ids"] = []
    if league_filter:
        data["population"]["league_ids"] = [record.context_jsonb["fixture_identity"]["league_id"]]
    definition = ExperimentDefinition.model_validate(data)
    cutoff = datetime.now(UTC)
    async with factory() as s:
        before = await plan_replay(s, definition, cutoff=cutoff)
    async with factory() as s, s.begin():
        other = League(slug="m9-review-" + uuid.uuid4().hex[:10], name="MUTABLE_NEW_LEAGUE")
        team = Team(name="MUTABLE_NEW_TEAM")
        s.add_all([other, team])
        await s.flush()
        for offset, fid in enumerate((record.fixture_id, missing.id)):
            await s.execute(
                update(Fixture)
                .where(Fixture.id == fid)
                .values(
                    kickoff_at=definition.population.end + timedelta(days=20 + offset),
                    league_id=other.id,
                    home_team_id=team.id,
                    status="PST",
                    venue="MUTABLE_NEW_VENUE",
                    round="NEW",
                )
            )
    async with factory() as s:
        after = await plan_replay(s, definition, cutoff=cutoff)
    assert after["counts"] == before["counts"]
    assert after["manifest"] == before["manifest"]
    assert str(missing.id) not in {item["fixture_id"] for item in after["manifest"]}
    assert str(record.fixture_id) in {item["fixture_id"] for item in after["manifest"]}


async def test_explicit_missing_fixture_is_counted_without_provider_backfill(
    factory, record, monkeypatch
):
    missing = await missing_fixture(factory, record)
    data = m9.definition(record).model_dump(mode="json")
    data["population"]["fixture_ids"] = [str(missing.id)]
    definition = ExperimentDefinition.model_validate(data)

    def forbidden(*a, **kw):
        pytest.fail("historical population must not backfill providers")

    monkeypatch.setattr(
        "sports_intelligence.providers.sports.factory.build_sports_provider", forbidden
    )
    async with factory() as s:
        ledger = await s.scalar(select(func.count()).select_from(ExternalApiRequest))
        plan = await plan_replay(s, definition)
        assert plan["counts"]["requested"] == plan["counts"]["non_replayable"] == 1
        assert plan["manifest"][0]["status"] == "NOT_REPLAYABLE"
        assert plan["manifest"][0]["fixture_id"] == str(missing.id)
        assert plan["counts"]["reasons"] == {"missing_frozen_context": 1}
        assert await s.scalar(select(func.count()).select_from(ExternalApiRequest)) == ledger


async def component_proposal(factory, record, settings, component):
    original, _, _, parent = await m9.proposal(factory, record, settings)
    async with factory() as s, s.begin():
        content = {**original.content_jsonb, "affected_component": component}
        row = ImprovementProposal(
            evidence_hash=fingerprint(
                {"synthetic": original.evidence_hash, "component": component}
            ),
            comparison_id=original.comparison_id,
            content_jsonb=content,
            evidence_jsonb=original.evidence_jsonb,
            analyst_jsonb=original.analyst_jsonb,
            sample_size=original.sample_size,
            status="PROPOSED",
        )
        s.add(row)
        await s.flush()
        return row, parent


async def assert_no_approval_writes(factory, proposal_id, experiments_before):
    async with factory() as s:
        row = await s.get(ImprovementProposal, proposal_id)
        assert row.status == "PROPOSED" and row.experiment_id is None
        assert await s.scalar(select(func.count()).select_from(ImprovementProposalEvent)) == 0
        assert await s.scalar(select(func.count()).select_from(Experiment)) == experiments_before


@pytest.mark.parametrize("component", COMPONENTS)
async def test_default_mapping_only_prompt_and_atomic_on_failure(
    factory, record, service_settings, component
):
    proposal, parent = await component_proposal(factory, record, service_settings, component)
    before = [
        Path(p).read_bytes()
        for p in (service_settings.llm_routes_path, service_settings.prediction_prompt_path)
    ]
    async with factory() as s:
        number = await s.scalar(select(func.count()).select_from(Experiment))
        action = ApproveRequest(actor="review-owner", reason="Reviewed proposal")
        if component == "prompt":
            approved = await approve_experiment(s, proposal, action, service_settings)
            await s.commit()
            exp = await s.get(Experiment, approved.experiment_id)
            assert approved.status == "APPROVED_FOR_EXPERIMENT"
            assert exp.definition_jsonb["treatment"]["prompt"] == "candidate"
            assert (
                exp.definition_jsonb["control"]["route"]
                == exp.definition_jsonb["treatment"]["route"]
            )
            arms = {
                a.name: a.frozen_jsonb
                for a in (
                    await s.scalars(
                        select(ExperimentArm).where(ExperimentArm.experiment_id == exp.id)
                    )
                ).all()
            }
            assert arms["control"]["models"] == arms["treatment"]["models"]
            assert arms["control"]["prompt_hash"] != arms["treatment"]["prompt_hash"]
            assert await s.scalar(select(func.count()).select_from(ExperimentRun)) == 1
        else:
            with pytest.raises(ValueError):
                await approve_experiment(s, proposal, action, service_settings)
            # Commit deliberately: service validation must not rely on HTTP exception rollback.
            await s.commit()
            await assert_no_approval_writes(factory, proposal.id, number)
    assert before == [
        Path(p).read_bytes()
        for p in (service_settings.llm_routes_path, service_settings.prediction_prompt_path)
    ]


@pytest.mark.parametrize("component", ["prompt", "model"])
async def test_explicit_reviewed_definition_matches_real_frozen_dimension(
    factory, record, service_settings, component
):
    proposal, _ = await component_proposal(factory, record, service_settings, component)
    treatment = (
        ArmRequest(route="prediction_primary", prompt="candidate")
        if component == "prompt"
        else ArmRequest(route="prediction_challenger")
    )
    reviewed = m9.definition(record, treatment=treatment).model_copy(
        update={"name": "Reviewed " + component, "created_by": "review-owner"}
    )
    async with factory() as s:
        approved = await approve_experiment(
            s,
            proposal,
            ApproveRequest(
                actor="review-owner", reason="Explicit reviewed definition", experiment=reviewed
            ),
            service_settings,
        )
        await s.commit()
        exp = await s.get(Experiment, approved.experiment_id)
        assert exp.definition_jsonb == reviewed.model_dump(mode="json")
        arms = {
            a.name: a.frozen_jsonb
            for a in (
                await s.scalars(select(ExperimentArm).where(ExperimentArm.experiment_id == exp.id))
            ).all()
        }
        if component == "model":
            assert arms["control"]["models"][0]["model"] != arms["treatment"]["models"][0]["model"]
            assert arms["control"]["prompt_hash"] == arms["treatment"]["prompt_hash"]
        else:
            assert arms["control"]["prompt_hash"] != arms["treatment"]["prompt_hash"]
            assert arms["control"]["models"] == arms["treatment"]["models"]
        run, _ = await request_run(s, exp, RunRequest(), service_settings)
        await s.commit()
    await m9.complete(factory, service_settings, run)
    async with factory() as s:
        assert (await s.get(ImprovementProposal, proposal.id)).status == "EXPERIMENT_RUNNING"


@pytest.mark.parametrize(
    "component,treatment",
    [
        ("model", ArmRequest(route="prediction_primary", prompt="candidate")),
        ("prompt", ArmRequest(route="prediction_challenger")),
        ("model", ArmRequest(route="prediction_primary")),
        ("prompt", ArmRequest(route="prediction_primary")),
        ("data_quality", ArmRequest(prompt="candidate")),
        ("features", ArmRequest(prompt="candidate")),
        ("ranking", ArmRequest(prompt="candidate")),
        ("sources", ArmRequest(prompt="candidate")),
    ],
)
async def test_unrelated_or_unsupported_explicit_definition_cannot_link_proposal(
    factory, record, service_settings, component, treatment
):
    proposal, _ = await component_proposal(factory, record, service_settings, component)
    reviewed = m9.definition(record, treatment=treatment).model_copy(
        update={"name": "Unrelated reviewed definition"}
    )
    async with factory() as s:
        number = await s.scalar(select(func.count()).select_from(Experiment))
        with pytest.raises(ValueError):
            await approve_experiment(
                s,
                proposal,
                ApproveRequest(actor="review-owner", reason="Invalid mapping", experiment=reviewed),
                service_settings,
            )
        await s.commit()
    await assert_no_approval_writes(factory, proposal.id, number)


@pytest.mark.parametrize("component", COMPONENTS)
async def test_telegram_actions_and_api_error_are_component_aware(
    factory, record, service_settings, component
):
    proposal, _ = await component_proposal(factory, record, service_settings, component)
    transport = FakeTransport()
    posts = []
    with TestClient(create_app(service_settings)) as client:
        response = client.get(f"/v1/improvements/{proposal.id}")
        assert response.json()["automatic_experiment_supported"] is (component == "prompt")

        def relay(request):
            import json

            if request.method == "POST":
                posts.append(request.url.path)
            result = client.request(
                request.method,
                request.url.path,
                json=json.loads(request.content) if request.content else None,
            )
            return httpx.Response(result.status_code, json=result.json())

        async with httpx.AsyncClient(transport=httpx.MockTransport(relay)) as http:
            context = AppContext(
                transport=transport,
                backend=BackendClient("https://synthetic.invalid", client=http),
                settings=service_settings,
                allowed_user_ids=frozenset({1}),
            )
            await experiment_callback(make_callback(f"m9:proposal:{proposal.id}"), context)
            callbacks = [
                b.callback_data
                for row in transport.edited[-1]["reply_markup"].inline_keyboard
                for b in row
            ]
            if component == "prompt":
                assert f"m9:approve:{proposal.id}" in callbacks
            else:
                assert f"m9:approve:{proposal.id}" not in callbacks
                assert "candidate prompt" not in transport.edited[-1]["text"]
                assert "ручн" in transport.edited[-1]["text"].lower()
                await experiment_callback(make_callback(f"m9:approve:{proposal.id}"), context)
                assert posts == []  # Old/stale callback cannot authorize an unrelated experiment.
        if component != "prompt":
            result = client.post(
                f"/v1/improvements/{proposal.id}/approve-experiment",
                json={"actor": "owner", "reason": "Needs reviewed mapping"},
            )
            assert result.status_code == 409 and result.json()["detail"] in (
                "manual_experiment_definition_required",
                "unsupported_proposal_experiment_component",
            )


@pytest.mark.parametrize("failure", ["missing_prompt", "unchanged_prompt"])
async def test_failed_prompt_instantiation_creates_no_partial_approval(
    factory, record, service_settings, tmp_path, failure
):
    proposal, _ = await component_proposal(factory, record, service_settings, "prompt")
    path = (
        str(tmp_path / "missing" / "1.1.0.txt")
        if failure == "missing_prompt"
        else service_settings.prediction_prompt_path
    )
    settings = service_settings.model_copy(update={"experiment_candidate_prompt_path": path})
    async with factory() as s:
        number = await s.scalar(select(func.count()).select_from(Experiment))
        with pytest.raises((ValueError, OSError)):
            await approve_experiment(
                s, proposal, ApproveRequest(actor="owner", reason="Unavailable candidate"), settings
            )
        await s.commit()
    await assert_no_approval_writes(factory, proposal.id, number)


async def test_model_route_alias_is_not_a_model_change(factory, record, service_settings, tmp_path):
    import yaml

    proposal, _ = await component_proposal(factory, record, service_settings, "model")
    config = yaml.safe_load(Path(service_settings.llm_routes_path).read_text())
    config["routes"]["same_model_alias"] = copy.deepcopy(config["routes"]["prediction_primary"])
    config["manual_override_routes"] = ["same_model_alias"]
    path = tmp_path / "routes.yaml"
    path.write_text(yaml.safe_dump(config))
    settings = service_settings.model_copy(update={"llm_routes_path": str(path)})
    reviewed = m9.definition(record, treatment=ArmRequest(route="same_model_alias"))
    async with factory() as s:
        number = await s.scalar(select(func.count()).select_from(Experiment))
        with pytest.raises(ValueError, match="incompatible_proposal_experiment_definition"):
            await approve_experiment(
                s,
                proposal,
                ApproveRequest(actor="owner", reason="No actual model change", experiment=reviewed),
                settings,
            )
        await s.commit()
    await assert_no_approval_writes(factory, proposal.id, number)


@pytest.mark.parametrize("component", ["prompt", "model"])
async def test_historical_declared_route_is_not_used_for_proposal_mapping(
    factory, record, service_settings, component
):
    proposal, _ = await component_proposal(factory, record, service_settings, component)
    treatment = (
        ArmRequest(route="prediction_primary", prompt="candidate")
        if component == "prompt"
        else ArmRequest(route="prediction_challenger")
    )
    reviewed = m9.definition(
        record, control=ArmRequest(source="historical_primary"), treatment=treatment
    )
    async with factory() as s:
        number = await s.scalar(select(func.count()).select_from(Experiment))
        with pytest.raises(ValueError, match="incompatible_proposal_experiment_definition"):
            await approve_experiment(
                s,
                proposal,
                ApproveRequest(
                    actor="owner", reason="Historical identity is per case", experiment=reviewed
                ),
                service_settings,
            )
        await s.commit()
    await assert_no_approval_writes(factory, proposal.id, number)


@pytest.mark.parametrize("status", ["APPROVED_FOR_EXPERIMENT", "EXPERIMENT_RUNNING"])
async def test_old_incompatible_lineage_cannot_advance_or_duplicate_approve(
    factory, record, service_settings, status
):
    from sports_intelligence.experiments.analyst import human_transition
    from sports_intelligence.experiments.contracts import HumanAction
    from sports_intelligence.experiments.service import create_experiment

    proposal, _ = await component_proposal(factory, record, service_settings, "model")
    prompt_definition = m9.definition(
        record, treatment=ArmRequest(route="prediction_primary", prompt="candidate")
    )
    async with factory() as s:
        prompt_experiment, _ = await create_experiment(s, prompt_definition, service_settings)
        # Simulate an artifact that the reviewed old default path could create. No evidence rewrite.
        await s.execute(
            update(ImprovementProposal)
            .where(ImprovementProposal.id == proposal.id)
            .values(status=status, experiment_id=prompt_experiment.id)
        )
        await s.commit()
        stored = await s.get(ImprovementProposal, proposal.id)
        runs_before = await s.scalar(select(func.count()).select_from(ExperimentRun))
        if status == "APPROVED_FOR_EXPERIMENT":
            with pytest.raises(ValueError):
                await approve_experiment(
                    s,
                    stored,
                    ApproveRequest(actor="owner", reason="Duplicate invalid legacy approval"),
                    service_settings,
                )
            with pytest.raises(ValueError):
                await request_run(s, prompt_experiment, RunRequest(), service_settings)
        else:
            with pytest.raises(ValueError):
                await human_transition(
                    s,
                    stored,
                    "PROMOTED",
                    HumanAction(actor="owner", reason="Cannot promote unrelated evidence"),
                )
        await s.commit()
        assert await s.scalar(select(func.count()).select_from(ExperimentRun)) == runs_before
        assert await s.scalar(select(func.count()).select_from(ImprovementProposalEvent)) == 0
        assert (
            stored.status == status
        )  # Retain the historical artifact; human rejection remains possible.
        await human_transition(
            s,
            stored,
            "REJECTED",
            HumanAction(actor="owner", reason="Reject invalid legacy mapping"),
        )
        await s.commit()


async def test_explicit_context_selection_and_missing_id_remain_strict(factory, record):
    data = m9.definition(record).model_dump(mode="json")
    absent = uuid.uuid4()
    data["population"].update(fixture_ids=[], context_ids=[str(record.id), str(absent)])
    async with factory() as s:
        plan = await plan_replay(s, ExperimentDefinition.model_validate(data))
    assert plan["counts"]["population_basis"] == "explicit_context_ids"
    assert plan["counts"]["requested"] == 2 and plan["counts"]["non_replayable"] == 1
    assert plan["manifest"][0]["control"]["context_id"] == str(record.id)
    assert plan["counts"]["reasons"] == {"context_outside_scope_or_missing": 1}
