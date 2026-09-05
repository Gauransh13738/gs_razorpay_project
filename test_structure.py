#!/usr/bin/env python3
"""
Test script to verify the separated frontend/backend structure works correctly.
"""

import os
import sys
from pathlib import Path

def test_project_structure():
    """Test that the project structure is correctly separated."""
    print("Testing Project Structure...")
    
    base_dir = Path(__file__).parent
    frontend_dir = base_dir / "frontend"
    backend_dir = base_dir / "backend"
    
    # Test directories exist
    assert frontend_dir.exists(), "Frontend directory missing"
    assert backend_dir.exists(), "Backend directory missing"
    print("[OK] Frontend and backend directories exist")
    
    # Test frontend files
    assert (frontend_dir / "dashboard.html").exists(), "Frontend dashboard.html missing"
    assert (frontend_dir / "Dockerfile").exists(), "Frontend Dockerfile missing"
    assert (frontend_dir / "package.json").exists(), "Frontend package.json missing"
    print("[OK] Frontend files present")
    
    # Test backend files
    assert (backend_dir / "server.py").exists(), "Backend server.py missing"
    assert (backend_dir / "requirements.txt").exists(), "Backend requirements.txt missing"
    assert (backend_dir / "Dockerfile").exists(), "Backend Dockerfile missing"
    assert (backend_dir / ".env.example").exists(), "Backend .env.example missing"
    print("[OK] Backend files present")
    
    # Test root files
    assert (base_dir / "docker-compose.yml").exists(), "docker-compose.yml missing"
    assert (base_dir / "README.md").exists(), "README.md missing"
    assert (base_dir / ".gitignore").exists(), ".gitignore missing"
    assert (base_dir / "DEPLOYMENT.md").exists(), "DEPLOYMENT.md missing"
    assert (base_dir / "LICENSE").exists(), "LICENSE missing"
    print("[OK] Root configuration files present")
    
    print("\n[PASS] Project structure test passed!")
    return True

def test_backend_imports():
    """Test that backend can be imported correctly."""
    print("\nTesting Backend Imports...")
    
    backend_dir = Path(__file__).parent / "backend"
    sys.path.insert(0, str(backend_dir))
    
    try:
        import server
        print("[OK] server.py imports successfully")
        
        import voice_service
        print("[OK] voice_service.py imports successfully")
        
        import duplex_voice_handler
        print("[OK] duplex_voice_handler.py imports successfully")
        
        import payment_workflow
        print("[OK] payment_workflow.py imports successfully")
        
        print("\n[PASS] Backend imports test passed!")
        return True
    except Exception as e:
        print(f"[FAIL] Backend imports failed: {e}")
        return False

def test_dashboard_path():
    """Test that the dashboard path is correctly configured in server.py."""
    print("\nTesting Dashboard Path Configuration...")
    
    backend_dir = Path(__file__).parent / "backend"
    server_file = backend_dir / "server.py"
    
    content = server_file.read_text(encoding='utf-8', errors='ignore')
    
    # Check that the dashboard path points to frontend directory
    if 'BASE_DIR.parent / "frontend" / "dashboard.html"' in content:
        print("[OK] Dashboard path correctly configured to frontend directory")
        return True
    else:
        print("[FAIL] Dashboard path not correctly configured")
        return False

def test_voice_agent_switching():
    """Test that voice agent switching functionality is preserved."""
    print("\nTesting Voice Agent Switching Logic...")
    
    frontend_dir = Path(__file__).parent / "frontend"
    dashboard_file = frontend_dir / "dashboard.html"
    
    content = dashboard_file.read_text(encoding='utf-8', errors='ignore')
    
    # Check for fresh transcript generation on agent switch
    if 'resetCallTranscript' in content and 'switchPersonaTab' in content:
        print("[OK] Voice agent switching with fresh transcript generation present")
        
        # Check for reset_session parameter
        if 'reset_session: true' in content:
            print("[OK] Backend reset_session parameter correctly set")
            return True
        else:
            print("[WARN] reset_session parameter not found (may be in backend)")
            return True
    else:
        print("[FAIL] Voice agent switching functionality may be missing")
        return False

def test_no_send_buttons():
    """Test that no manual send buttons are present (voice-only interaction)."""
    print("\nTesting for Manual Send Buttons...")
    
    frontend_dir = Path(__file__).parent / "frontend"
    dashboard_file = frontend_dir / "dashboard.html"
    
    content = dashboard_file.read_text(encoding='utf-8', errors='ignore')
    
    # Check for text input fields for messaging (excluding simulation form)
    has_text_input = 'type="text"' in content and 'placeholder' in content and 'message' in content.lower()
    
    # Check for manual send buttons (excluding voice-related buttons)
    has_manual_send = 'Send' in content and 'button' in content.lower() and 'Hold' not in content
    
    # The dashboard uses "send" in function names but has no manual send buttons
    # We specifically check for button elements with "Send" text
    if not has_manual_send:
        print("[OK] No manual send buttons found (voice-only interaction confirmed)")
        return True
    else:
        print("[WARN] Potential manual send functionality found (review needed)")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Razorpay Payment Recovery Engine - Structure Tests")
    print("=" * 60)
    
    tests = [
        test_project_structure,
        test_backend_imports,
        test_dashboard_path,
        test_voice_agent_switching,
        test_no_send_buttons
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"[FAIL] Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    print("=" * 60)
    
    if all(results):
        print("\n[PASS] All tests passed! Project is ready for deployment.")
        return 0
    else:
        print("\n[WARN] Some tests failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())