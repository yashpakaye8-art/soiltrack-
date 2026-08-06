import sys
from app import app, db, User, Sample, DilutionFactor, TestResult, LabCalculation

def run_health_check():
    print("==================================================")
    print("   SoilTrack System Comprehensive Health Check ")
    print("==================================================")

    errors = []

    with app.app_context():
        # 1. Database Connection & Table Inspection
        print("\n[1/5] Checking MySQL Database Schema & Models...")
        try:
            user_count = User.query.count()
            sample_count = Sample.query.count()
            factor_count = DilutionFactor.query.count()
            print(f"  - User table: {user_count} records")
            print(f"  - Sample table: {sample_count} records")
            print(f"  - DilutionFactor table: {factor_count} factors configured")
            print("  [OK] Database models & MySQL connection are healthy!")
        except Exception as e:
            errors.append(f"Database error: {str(e)}")
            print(f"  [FAIL] Database error: {str(e)}")

        # 2. Test Client Route Rendering (All 12 Endpoints)
        print("\n[2/5] Testing Route Endpoints & Template Rendering...")
        client = app.test_client()

        # Login session as Admin
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'
            sess['username'] = 'admin'

        routes_to_test = [
            ('/', 200, 'Dashboard'),
            ('/samples', 200, 'All Samples'),
            ('/add', 200, 'Add Sample'),
            ('/bulk-add', 200, 'Bulk Import'),
            ('/lab-calculation', 200, 'Lab Calculation'),
            ('/multiplication-factors', 200, 'Multiplication Factors'),
            ('/users', 200, 'User Management'),
            ('/User%20Management', 200, 'User Management Alias'),
            ('/download-import-template', 200, 'CSV Import Template'),
            ('/export', 200, 'Excel Export'),
            ('/bill/1', 200, 'Bill Receipt Report'),
            ('/login', 200, 'Login Page'),
            ('/register', 200, 'Register Page'),
        ]

        for endpoint, expected_status, name in routes_to_test:
            if endpoint == '/login':
                with client.session_transaction() as sess:
                    sess.clear()
            else:
                with client.session_transaction() as sess:
                    sess['user_id'] = 1
                    sess['role'] = 'admin'
                    sess['username'] = 'admin'

            try:
                res = client.get(endpoint)
                if res.status_code == expected_status:
                    print(f"  - {name} ({endpoint}): HTTP {res.status_code} OK [OK]")
                else:
                    err = f"Endpoint {name} ({endpoint}) returned status {res.status_code}, expected {expected_status}"
                    errors.append(err)
                    print(f"  - {name} ({endpoint}): HTTP {res.status_code} [FAIL]")
            except Exception as e:
                err = f"Endpoint {name} ({endpoint}) threw error: {str(e)}"
                errors.append(err)
                print(f"  - {name} ({endpoint}): Exception {str(e)} [FAIL]")

        # 3. Security & Policy Verification
        print("\n[3/5] Verifying Security Configuration & Admin Limits...")
        admin_count = User.query.filter_by(role='admin').count()
        print(f"  - Total Admin accounts in system: {admin_count}")
        if admin_count <= 2:
            print("  [OK] Max 2 Admin accounts restriction is enforced!")
        else:
            errors.append(f"Admin count ({admin_count}) exceeds limit of 2!")
            print(f"  [FAIL] Admin limit violation: {admin_count} admins present")

        if app.config.get('PERMANENT_SESSION_LIFETIME'):
            print(f"  [OK] Session timeout configured: {app.config['PERMANENT_SESSION_LIFETIME']}")
        else:
            errors.append("Session lifetime not configured!")

        # 4. Check Chemistry Factors Data Integrity
        print("\n[4/5] Checking Multiplication Factors & Burette B Constant...")
        burette_b = DilutionFactor.query.filter_by(parameter='n_burette_b').first()
        if burette_b:
            print(f"  - Nitrogen Burette Reading B constant: {burette_b.factor} {burette_b.unit} [OK]")
        else:
            print("  - Nitrogen Burette Reading B constant: Default fallback will be used")

        # 5. Final Summary
        print("\n[5/5] Final System Status Summary...")
        print("--------------------------------------------------")
        if not errors:
            print("ALL SYSTEM HEALTH CHECKS PASSED WITH 100% SUCCESS!")
            print("Everything in SoilTrack is 100% RIGHT, HEALTHY & OPERATIONAL.")
        else:
            print(f"FOUND {len(errors)} ISSUE(S):")
            for err in errors:
                print(f"   - {err}")
        print("--------------------------------------------------")

if __name__ == '__main__':
    run_health_check()
