from app.db.session import Base

# Export Base so migrations and models can reference it
__all__ = ["Base"]
