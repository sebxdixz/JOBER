"""Test full flow: search → scrape → generate CV+CL → export PDF."""

import asyncio
import sys
import os

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

from jober.agents.autonomous_search import search_getonbrd, search_linkedin
from jober.agents.job_scraper import job_scraper_node
from jober.agents.cv_writer import cv_writer_node
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro, save_application_output_async


async def main():
    print("=== Test Full Flow ===\n")

    # Load profile
    perfil = load_perfil_maestro()
    if not perfil:
        print("ERROR: No profile found. Run jober init first.")
        return
    print(f"Profile: {perfil.nombre} - {perfil.titulo_profesional}\n")

    # 1. Search GetOnBrd
    print("[1/5] Searching GetOnBrd for 'AI Engineer'...")
    getonbrd_urls = await search_getonbrd(["AI", "Engineer", "Python"], max_results=5)
    print(f"  Found {len(getonbrd_urls)} URLs")
    for u in getonbrd_urls[:3]:
        print(f"    - {u}")

    # 2. Search LinkedIn
    print("\n[2/5] Searching LinkedIn for 'AI Engineer'...")
    linkedin_urls = await search_linkedin(["AI", "Engineer", "Python"], max_results=5)
    print(f"  Found {len(linkedin_urls)} URLs")
    for u in linkedin_urls[:3]:
        print(f"    - {u}")

    # 3. Pick first URL and scrape
    all_urls = getonbrd_urls + linkedin_urls
    if not all_urls:
        print("\nNo URLs found on any platform. Exiting.")
        return

    test_url = all_urls[0]
    print(f"\n[3/5] Scraping: {test_url}")
    state = JoberState(job_url=test_url, perfil=perfil)
    scrape_result = await job_scraper_node(state)

    if scrape_result.get("error"):
        print(f"  ERROR: {scrape_result['error']}")
        return

    oferta = scrape_result["oferta"]
    print(f"  Title: {oferta.titulo}")
    print(f"  Company: {oferta.empresa}")
    print(f"  Location: {oferta.ubicacion}")
    print(f"  Modality: {oferta.modalidad}")
    print(f"  Requirements: {len(oferta.requisitos)}")

    # 4. Generate CV + Cover Letter + Match
    print(f"\n[4/5] Generating CV + Cover Letter + Match Analysis...")
    state_with_offer = JoberState(job_url=test_url, perfil=perfil, oferta=oferta)
    writer_result = await cv_writer_node(state_with_offer)

    if writer_result.get("error"):
        print(f"  ERROR: {writer_result['error']}")
        return

    docs = writer_result["documentos"]
    print(f"  CV length: {len(docs.cv_adaptado_md)} chars")
    print(f"  Cover letter length: {len(docs.cover_letter_md)} chars")
    print(f"  Match score: {docs.match_score:.0%}")
    print(f"  Analysis: {docs.analisis_fit[:150]}...")

    # 5. Save (Markdown + PDF)
    print(f"\n[5/5] Saving documents (MD + PDF)...")
    output_dir = await save_application_output_async(oferta, docs)
    print(f"  Output directory: {output_dir}")

    # List generated files
    for f in sorted(output_dir.iterdir()):
        size = f.stat().st_size
        print(f"    {f.name} ({size:,} bytes)")

    print("\n=== Full Flow Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
