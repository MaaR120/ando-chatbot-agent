from app.core.database import get_db
from app.schemas.recommendation_history import HistoryRecommendationRequest
from app.services.history_recommendation_service import HistoryRecommendationService

try:
    db = next(get_db())
    req = HistoryRecommendationRequest(user_id="44ef4cad-2013-46af-8bab-74875076667b", limit=10, include_visited=False)
    service = HistoryRecommendationService(db=db)
    res = service.get_history_recommendations(req, db=db)
    print("Success:", res)
except Exception as e:
    import traceback
    traceback.print_exc()
