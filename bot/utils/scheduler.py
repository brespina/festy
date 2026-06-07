"""APScheduler wrapper. Cogs register jobs via the shared scheduler instance."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
