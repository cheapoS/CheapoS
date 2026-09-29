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
    """A role-aware catalog prior; callers rank real outcomes ahead of this.

    The role-specific benchmark stays primary (coding for workers/reviewers,
    agentic for planners). General intelligence breaks ties between models
    with the same primary score; it does not replace evidence from CheapOS runs.
    """
    data = model.get('benchmarks') or {}
    metric = 'agentic' if role == 'planner' else 'coding'
    trusted = isinstance(data, dict) and data.get('source') == SOURCE and not (model.get('metadata_evidence') or {}).get('stale')
    score = data.get(metric) if trusted else None
    intelligence = data.get('intelligence') if trusted else None
    known = valid_score(score)
    known_intelligence = valid_score(intelligence)
    return (0 if known else 1, -score if known else 0,
            0 if known_intelligence else 1, -intelligence if known_intelligence else 0)
