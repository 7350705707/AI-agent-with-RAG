"""Entry-point for running with:  python run.py"""

import logging
import uvicorn

from app.config import SERVER_HOST, SERVER_PORT, LOG_LEVEL

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        workers=1,
        log_level=LOG_LEVEL.lower(),
    )
