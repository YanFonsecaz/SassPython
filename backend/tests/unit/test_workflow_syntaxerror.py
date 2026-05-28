def test_workflow_imports():
    import app.agents.workflow

    assert hasattr(app.agents.workflow, "executar_workflow_completo")
    assert hasattr(app.agents.workflow, "retomar_workflow")
    assert hasattr(app.agents.workflow, "criar_workflow")


def test_workflow_inlinks_imports():
    import app.agents.workflow_inlinks

    assert hasattr(app.agents.workflow_inlinks, "executar_workflow_inlinks")


def test_workflow_inlinks_reversos_imports():
    import app.agents.workflow_inlinks_reversos

    assert hasattr(app.agents.workflow_inlinks_reversos, "executar_workflow_distribuir_inlinks")


def test_worker_imports():
    import app.worker

    assert hasattr(app.worker, "WorkerSettings")
    ws = app.worker.WorkerSettings()
    assert len(ws.functions) == 5
    assert ws.max_tries == 3
    assert ws.job_timeout > 0


def test_main_app_creates():
    from app.main import application

    assert application.title == "SEO SaaS IA"
    assert application.version == "1.0.0"
