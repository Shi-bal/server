"""
VenomX Development Server Starter
Run this to test your VenomX backend without AI models
"""

import subprocess
import sys
import os

def main():
    print("🚀 Starting VenomX Development Server...")
    print("📍 This will start the server without AI models for testing")
    print("🌐 Server will be available at: http://localhost:8000")
    print("📚 API docs will be at: http://localhost:8000/docs")
    print("\n⏹️  Press Ctrl+C to stop the server\n")
    
    # Change to the server directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Get the Python executable path
    python_exe = os.path.join(".venv", "Scripts", "python.exe")
    
    try:
        # Start the development server
        subprocess.run([
            python_exe, "-m", "uvicorn", "main_dev:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except FileNotFoundError:
        print("❌ Error: Python virtual environment not found")
        print("💡 Make sure you're in the correct directory and the .venv folder exists")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    main()