"""Legacy router alias; canonical routes live in ingenuity.web.server."""
from ingenuity.web.server import app
router = app.router
