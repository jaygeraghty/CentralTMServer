from app import app
import cif_parser

with app.app_context():
    cif_parser.process_cif_files()