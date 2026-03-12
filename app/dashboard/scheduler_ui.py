from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from app.dashboard.common import check_admin, templates
from app.scheduler import scheduler_service, get_scheduler_status

router = APIRouter()


@router.get("/scheduler", dependencies=[Depends(check_admin)])
async def scheduler_page(request: Request):
    status = get_scheduler_status()
    return templates.TemplateResponse("dashboard/scheduler.html", {"request": request, "jobs": status})


@router.get("/scheduler/status", dependencies=[Depends(check_admin)])
async def scheduler_status_api():
    return JSONResponse(get_scheduler_status())


@router.post("/scheduler/run/{job_name}", dependencies=[Depends(check_admin)])
async def scheduler_run_job(job_name: str):
    method = getattr(scheduler_service, f"job_{job_name}", None)
    if not method:
        return JSONResponse({"ok": False, "error": "Unknown job"}, status_code=404)
    import asyncio
    asyncio.create_task(method())
    return JSONResponse({"ok": True, "message": f"Job {job_name} triggered"})
