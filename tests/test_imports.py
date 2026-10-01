"""Verify all major modules import without error."""


def test_config():
    import config
    assert config.ASSETS == ["XAU", "XAG"]
    assert len(config.HORIZONS) == 5
    assert len(config.FX_PAIRS) == 5


def test_db_schema():
    from db.schema import init_db
    assert callable(init_db)


def test_db_ops():
    from db import ops
    assert callable(ops.insert_forecast)
    assert callable(ops.get_pending_forecasts)
    assert callable(ops.insert_forecast_outcome)


def test_providers():
    from data.providers.metals_futures import MetalsFuturesProvider
    from data.providers.forex import YFinanceFXProvider, get_all_fx_latest
    from data.providers.news import get_news, VERIFIED_SOURCES
    assert len(VERIFIED_SOURCES) > 0


def test_models():
    from models.features import build_features, get_feature_names
    from models.forecaster import run_forecast
    from models.backtest import run_backtest
    from models.grader import grade_pending
    assert callable(build_features)
    assert callable(run_forecast)
    assert callable(run_backtest)
    assert callable(grade_pending)


def test_llm():
    from llm.ollama_client import is_online, analyse_news
    from llm.llm_registry import LLM_MODELS, DEFAULT_MODEL_KEY
    assert DEFAULT_MODEL_KEY in LLM_MODELS


def test_no_provider_chain():
    """ProviderChain was removed as dead code — confirm it's gone."""
    import data.providers.base as base
    assert not hasattr(base, "ProviderChain")
