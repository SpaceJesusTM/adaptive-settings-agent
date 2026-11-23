"""Service container wiring the catalogue, store and domain/agent services together."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .agent.runner import AgentRunner, ModelFactory
from .agent.graph import make_chat_models
from .catalog.loader import CatalogRegistry, load_registry
from .config import Settings, get_settings
from .domain.crosshair import CrosshairProfileService
from .domain.profile import ProfileService
from .domain.proposals import ProposalService
from .domain.recommender import RelevantNowService
from .domain.scenarios import ensure_seeded
from .domain.store import Store


@dataclass
class Services:
    settings: Settings
    registry: CatalogRegistry
    store: Store
    profile: ProfileService
    proposals: ProposalService
    relevant_now: RelevantNowService
    runner: AgentRunner
    crosshair: CrosshairProfileService


def build_services(settings: Optional[Settings] = None, *, model_factory: ModelFactory = make_chat_models,
                   seed: bool = True) -> Services:
    settings = settings or get_settings()
    registry = load_registry(settings.catalog_dir)
    store = Store(settings.db_path, registry)
    if seed:
        ensure_seeded(store, settings.scenario_dir, settings.backup_dir)
    profile = ProfileService(store)
    proposals = ProposalService(store, profile)
    relevant_now = RelevantNowService(store, profile)
    runner = AgentRunner(store, profile, settings, model_factory=model_factory, proposals=proposals, relevant_now=relevant_now)
    crosshair = CrosshairProfileService(store)
    return Services(settings=settings, registry=registry, store=store, profile=profile, proposals=proposals,
                    relevant_now=relevant_now, runner=runner, crosshair=crosshair)
