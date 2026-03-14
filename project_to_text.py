import os

# Files or folders to skip
IGNORE = {'.git', '__pycache__', 'Outputs', 'Data', 'project_to_text.py'}

def summarize_project():
    with open("full_project_context.txt", "w", encoding="utf-8") as f:
        for root, dirs, files in os.walk("."):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE]
            
            for file in files:
                if file.endswith(".py") and file not in IGNORE:
                    filepath = os.path.join(root, file)
                    f.write(f"\n{'='*50}\n")
                    f.write(f"FILE: {filepath}\n")
                    f.write(f"{'='*50}\n\n")
                    with open(filepath, 'r', encoding="utf-8") as code_file:
                        f.write(code_file.read())
                        f.write("\n")

if __name__ == "__main__":
    summarize_project()
    print("✅ Done! Copy everything from 'full_project_context.txt'")