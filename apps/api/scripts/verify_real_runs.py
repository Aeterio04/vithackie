import pypdf
from pathlib import Path
from kawach.execution.report_generator import generate_all_reports
from kawach.storage.artifacts import run_dir

runs = ["20261024-195639-82ad", "20261024-195152-3688"]

for r_id in runs:
    res = generate_all_reports(r_id, force_regenerate=True)
    r_dir = run_dir(r_id)
    md_path = r_dir / "report.md"
    pdf_path = r_dir / "report.pdf"
    files_md = r_dir / "files" / "report.md"
    files_pdf = r_dir / "files" / "report.pdf"

    print(f"==================================================")
    print(f"RUN: {r_id}")
    print(f"Status: {res.get('status')}")
    print(f"report.md: {md_path.resolve()} ({md_path.stat().st_size} bytes)")
    print(f"report.pdf: {pdf_path.resolve()} ({pdf_path.stat().st_size} bytes)")
    print(f"files/report.md: {files_md.resolve()} ({files_md.stat().st_size} bytes)")
    print(f"files/report.pdf: {files_pdf.resolve()} ({files_pdf.stat().st_size} bytes)")

    reader = pypdf.PdfReader(str(pdf_path))
    print(f"PDF Page count: {len(reader.pages)}")
    print("Section Outline from Markdown Headings:")
    headings = [line for line in md_path.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
    for h in headings:
        print("  ", h)

    # Sample extracted text from first 2 PDF pages
    pdf_sample = "\n".join(reader.pages[0].extract_text().splitlines()[:8])
    print(f"PDF Page 1 Header Extraction:\n{pdf_sample}")
    print()
