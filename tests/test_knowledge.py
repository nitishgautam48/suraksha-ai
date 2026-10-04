import pymupdf
import pytest

from backend.rag import fetcher, loaders, store


@pytest.fixture
def fake_vector_store(monkeypatch):
    """In-memory replacement for ChromaDB + the embedding model."""
    chunks: dict[str, dict] = {}
    monkeypatch.setattr(
        store,
        "upsert",
        lambda ids, embeddings, documents, metadatas: chunks.update(
            {i: {"text": d, "meta": m} for i, d, m in zip(ids, documents, metadatas, strict=True)}
        ),
    )
    monkeypatch.setattr(
        store, "delete_doc", lambda key: [chunks.pop(k) for k in [k for k, v in chunks.items() if v["meta"]["doc"] == key]]
    )

    class FakeOllama:
        def embed(self, texts):
            return [[0.1] * 8 for _ in texts]

    monkeypatch.setattr("backend.rag.ingest.get_ollama", lambda: FakeOllama())
    return chunks


def _pdf(text_pages):
    doc = pymupdf.open()
    for text in text_pages:
        doc.new_page().insert_text((72, 72), text, fontsize=11)
    doc.set_metadata({"title": "RBI Fraud Booklet"})
    return doc.tobytes()


def test_pdf_loader_keeps_pages():
    loaded = loaders.load_bytes(
        _pdf(["Never share your OTP with anyone at all.", "Report fraud to 1930 immediately please."]), "pdf"
    )
    assert loaded.pages == 2
    assert "## Page 1" in loaded.body and "## Page 2" in loaded.body
    assert loaded.meta["title"] == "RBI Fraud Booklet"


def test_html_loader_strips_chrome():
    html = (
        b"<html><head><title>UPI Safety</title><script>evil()</script></head><body><nav>Menu</nav>"
        b"<h1>UPI tips</h1><p>Never enter your PIN to receive money.</p><footer>(c)</footer></body></html>"
    )
    loaded = loaders.load_bytes(html, "html")
    assert loaded.meta["title"] == "UPI Safety"
    assert "# UPI tips" in loaded.body and "Never enter your PIN" in loaded.body
    assert "evil" not in loaded.body and "Menu" not in loaded.body


@pytest.mark.parametrize("url", ["http://example.com/x.pdf", "https://127.0.0.1/x", "https://localhost/x", "ftp://x"])
def test_fetcher_blocks_insecure_or_internal_urls(url):
    with pytest.raises(fetcher.FetchError):
        fetcher._check_public_https(url)


def test_admin_upload_index_and_delete(client, register, fake_vector_store, monkeypatch):
    from backend.database.session import SessionLocal
    from backend.models import KnowledgeDocument, User
    from backend.rag.ingest import ingest_document
    from backend.services import knowledge_service

    def run_now(doc_id):
        with SessionLocal() as db:
            ingest_document(db, db.get(KnowledgeDocument, doc_id))

    monkeypatch.setattr(knowledge_service, "_queue_ingest", run_now)
    data = register("kb-admin@example.com")
    with SessionLocal() as db:
        db.get(User, __import__("uuid").UUID(data["user"]["id"])).role = "admin"
        db.commit()
    h = {"Authorization": "Bearer " + register("kb-user@example.com")["access_token"]}
    files = {
        "file": (
            "booklet.pdf",
            _pdf(["Guaranteed returns are a red flag for investors.", "Verify advisers on SEBI."]),
            "application/pdf",
        )
    }
    form = {"title": "Investor Booklet", "source": "SEBI", "topic": "scam_detection"}
    assert client.post("/admin/knowledge/documents", headers=h, files=files, data=form).status_code == 403

    token = client.post("/auth/login", json={"email": "kb-admin@example.com", "password": "Passw0rd!x"}).json()["access_token"]
    ah = {"Authorization": f"Bearer {token}"}
    r = client.post("/admin/knowledge/documents", headers=ah, files=files, data=form)
    assert r.status_code == 202, r.text
    docs = client.get("/admin/knowledge/documents", headers=ah).json()
    doc = next(d for d in docs if d["title"] == "Investor Booklet")
    assert doc["status"] == "ingested" and doc["chunks"] >= 1 and doc["pages"] == 2
    pages = {c["meta"]["page"] for c in fake_vector_store.values() if c["meta"]["doc"] == doc["doc_key"]}
    assert pages == {1, 2}

    # re-ingest replaces chunks instead of duplicating them
    before = len(fake_vector_store)
    client.post(f"/admin/knowledge/documents/{doc['id']}/reingest", headers=ah)
    assert len(fake_vector_store) == before

    bad = client.post(
        "/admin/knowledge/documents", headers=ah, files={"file": ("x.exe", b"MZ", "application/octet-stream")}, data=form
    )
    assert bad.status_code == 415
    assert client.delete(f"/admin/knowledge/documents/{doc['id']}", headers=ah).status_code == 200
    assert not any(c["meta"]["doc"] == doc["doc_key"] for c in fake_vector_store.values())
