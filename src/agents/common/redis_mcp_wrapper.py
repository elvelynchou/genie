import sys
import os
import json

# Ensure we are in the correct directory
PROJECT_ROOT = "/etc/myapp/genie"
os.chdir(PROJECT_ROOT)

def run():
    try:
        # Import the main function from the package
        # We must use the package's internal logic to avoid stdout noise
        from redis_mcp_server.main import main
        
        # Prepare arguments for the click-based CLI
        sys.argv = ["redis-mcp-server", "--url", "redis://127.0.0.1:6379/0"]
        
        # Execute the server
        main()
    except Exception as e:
        sys.stderr.write(f"Wrapper Error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    run()
