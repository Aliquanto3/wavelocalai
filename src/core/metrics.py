from dataclasses import dataclass
import time

@dataclass
class InferenceMetrics:
    """Structure standard pour les métriques d'inférence"""
    model_name: str
    input_tokens: int
    output_tokens: int
    total_duration_s: float
    load_duration_s: float
    tokens_per_second: float
    model_size_gb: float = 0.0 # Rempli via la config
    
    # Placeholder pour le Green IT (Module futur)
    energy_wh: float = None
    carbon_g: float = None

class MetricsCalculator:
    """Helper pour mesurer le temps d'exécution"""
    def __init__(self):
        self.start_time = 0.0
        self.end_time = 0.0
        
    def start(self):
        self.start_time = time.perf_counter()
        
    def stop(self):
        self.end_time = time.perf_counter()
        
    @property
    def duration(self):
        return self.end_time - self.start_time