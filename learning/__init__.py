"""Learning package: local adaptive ML engine."""
from __future__ import annotations

from .backtest_engine import BacktestConfig, BacktestResult, BacktestTrade, HistoricalBacktester, StrategyLaboratory
from .dataset_builder import DatasetBuilder
from .feature_engine import FeatureEngine
from .model_manager import EvaluationResult, ModelManager, PromotionCriteria
from .outcome_labeler import OutcomeLabeler
from .performance_analyzer import PerformanceAnalyzer
from .predictor import Predictor
from .strategy_evolution import (
    EVOLUTION_SPACE,
    ExperimentConfig,
    ExperimentRegistry,
    ExperimentResult,
    ExperimentStatus,
    ExperimentType,
    SAFETY_BOUNDARIES,
    StrategyEvolutionEngine,
)
from .trainer import LearningOrchestrator, ModelTrainer
from .walkforward_validator import WalkForwardValidator

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "DatasetBuilder",
    "EvaluationResult",
    "EVOLUTION_SPACE",
    "ExperimentConfig",
    "ExperimentRegistry",
    "ExperimentResult",
    "ExperimentStatus",
    "ExperimentType",
    "FeatureEngine",
    "HistoricalBacktester",
    "LearningOrchestrator",
    "ModelManager",
    "ModelTrainer",
    "OutcomeLabeler",
    "PerformanceAnalyzer",
    "PromotionCriteria",
    "Predictor",
    "SAFETY_BOUNDARIES",
    "StrategyEvolutionEngine",
    "StrategyLaboratory",
    "WalkForwardValidator",
]