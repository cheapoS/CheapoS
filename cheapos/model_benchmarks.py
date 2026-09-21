"""Optional catalog priors, separate from observed cheapoS task outcomes."""
import math

SOURCE = 'Artificial Analysis'
METRICS = ('coding', 'agentic', 'intelligence')


def valid_score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def normalize(raw, catalog, refreshed_at):
    """Preserve only recognized indices; refresh time is not a benchmark date."""
    data = raw.get('artificial_analysis') if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        return None
    scores = {key: data[key + '_index'] for key in METRICS
              if valid_score(data.get(key + '_index'))}
    return {'source': SOURCE, 'catalog': catalog, 'refreshed_at': refreshed_at,
            **scores} if scores else None


def preference(model, role):
    """A starting preference only; callers rank real outcomes ahead of this."""
    data = model.get('benchmarks') or {}
    metric = 'agentic' if role == 'planner' else 'coding'
    score = data.get(metric) if isinstance(data, dict) and data.get('source') == SOURCE else None
    known = valid_score(score) and not (model.get('metadata_evidence') or {}).get('stale')
    return (0, -score) if known else (1, 0)
