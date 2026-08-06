import csv
import io
import openpyxl
from app import app, db, Sample

def test_bulk_import():
    print("--- Starting Bulk Import Automated Verification ---")

    with app.app_context():
        app.config['WTF_CSRF_ENABLED'] = False
        initial_count = Sample.query.count()
        print(f"Initial sample count in DB: {initial_count}")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'
            sess['username'] = 'admin'

        # 1. Test CSV Download Template
        r_tmpl = client.get('/download-import-template')
        assert r_tmpl.status_code == 200, "Template download failed"
        assert b"village,farmer_name" in r_tmpl.data, "Template data incorrect"
        print("[OK] Template download verified!")

        # 2. Test Bulk CSV Upload & Mapping (50 samples)
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(['CustomVillageCol', 'CustomFarmerCol', 'CustomPhoneCol', 'CustomAddrCol', 'CustomSurveyCol', 'CustomSourceCol', 'CustomSchemeCol', 'CustomCropCol', 'CustomFeeCol', 'CustomDateCol'])
        
        for i in range(1, 51):
            writer.writerow([
                'MappedVillageA',
                f'Farmer A{i}',
                f'98765432{i:02d}',
                f'Plot {i}',
                f'S-{100+i}',
                'govt' if i % 2 == 0 else 'private',
                'PM-KISAN' if i % 2 == 0 else '',
                'Rice',
                '0' if i % 2 == 0 else '200',
                '2026-07-30'
            ])

        csv_bytes = csv_buffer.getvalue().encode('utf-8')
        r_step1 = client.post('/bulk-add', data={
            'file': (io.BytesIO(csv_bytes), 'test_50_custom_cols.csv')
        }, content_type='multipart/form-data')

        assert r_step1.status_code == 200, f"Step 1 CSV upload failed: {r_step1.status_code}"
        assert b"Map Columns" in r_step1.data, "Step 2 mapping page not rendered"
        print("[OK] Step 1 CSV Upload rendered column mapping step successfully!")

        # Extract temp_filename from response
        html_str = r_step1.data.decode('utf-8')
        temp_filename = html_str.split('name="temp_filename" value="')[1].split('"')[0]

        # Step 2: Confirm Column Mapping
        r_step2 = client.post('/bulk-process', data={
            'temp_filename': temp_filename,
            'map_village': 'CustomVillageCol',
            'map_farmer_name': 'CustomFarmerCol',
            'map_phone_number': 'CustomPhoneCol',
            'map_address': 'CustomAddrCol',
            'map_survey_number': 'CustomSurveyCol',
            'map_sample_source': 'CustomSourceCol',
            'map_scheme': 'CustomSchemeCol',
            'map_crop': 'CustomCropCol',
            'map_testing_fee': 'CustomFeeCol',
            'map_collection_date': 'CustomDateCol'
        }, follow_redirects=True)

        assert r_step2.status_code == 200, f"Step 2 processing failed: {r_step2.status_code}"
        count_after_csv = Sample.query.count()
        print(f"Sample count after CSV column mapping import: {count_after_csv} (+{count_after_csv - initial_count})")
        assert count_after_csv == initial_count + 50, "CSV bulk import count mismatch!"
        print("[OK] 50-row CSV Column Mapping Import successfully created records and auto-generated Sample IDs!")

        # 3. Test Bulk Excel (.xlsx) Upload & Mapping (50 samples)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['GaonName', 'KisanName', 'MobileNo', 'Pata', 'GatNo', 'Category', 'Yojana', 'Piq', 'Cost', 'Tariqh'])

        for i in range(1, 51):
            ws.append([
                'MappedVillageB',
                f'Farmer B{i}',
                f'91234567{i:02d}',
                f'Sector {i}',
                f'S-{200+i}',
                'govt' if i % 2 == 0 else 'private',
                'Soil Scheme' if i % 2 == 0 else '',
                'Wheat',
                '0' if i % 2 == 0 else '250',
                '2026-07-30'
            ])

        xlsx_buffer = io.BytesIO()
        wb.save(xlsx_buffer)
        xlsx_bytes = xlsx_buffer.getvalue()

        r_xl_step1 = client.post('/bulk-add', data={
            'file': (io.BytesIO(xlsx_bytes), 'test_50_custom_cols.xlsx')
        }, content_type='multipart/form-data')

        assert r_xl_step1.status_code == 200, f"Step 1 Excel upload failed: {r_xl_step1.status_code}"
        xl_html = r_xl_step1.data.decode('utf-8')
        xl_temp_filename = xl_html.split('name="temp_filename" value="')[1].split('"')[0]

        r_xl_step2 = client.post('/bulk-process', data={
            'temp_filename': xl_temp_filename,
            'map_village': 'GaonName',
            'map_farmer_name': 'KisanName',
            'map_phone_number': 'MobileNo',
            'map_address': 'Pata',
            'map_survey_number': 'GatNo',
            'map_sample_source': 'Category',
            'map_scheme': 'Yojana',
            'map_crop': 'Piq',
            'map_testing_fee': 'Cost',
            'map_collection_date': 'Tariqh'
        }, follow_redirects=True)

        assert r_xl_step2.status_code == 200, f"Step 2 Excel processing failed: {r_xl_step2.status_code}"
        count_after_xlsx = Sample.query.count()
        print(f"Sample count after Excel column mapping import: {count_after_xlsx} (+{count_after_xlsx - count_after_csv})")
        assert count_after_xlsx == count_after_csv + 50, "Excel bulk import count mismatch!"
        print("[OK] 50-row Excel (.xlsx) Column Mapping Import successfully created records and auto-generated Sample IDs!")

        # Clean up test bulk records
        Sample.query.filter(Sample.village.in_(['MappedVillageA', 'MappedVillageB'])).delete()
        db.session.commit()
        print("[CLEANUP] Cleaned up test bulk import records.")

        print("\nALL BULK IMPORT COLUMN MAPPING TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_bulk_import()
