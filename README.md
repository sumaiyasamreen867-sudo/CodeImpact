The Core Purpose : CodeImpact is an intelligent developer tool that acts like an early warning system for code changes.

The Problem It Solves : In large software projects, modifying one function can accidentally break other parts of the code far away. CodeImpact automatically tracks Git commits to see what changed and maps out the ripple effects (both direct and indirect impacts) before code gets merged.
Git Change Tracking: Automatically reads Git history (like comparing HEAD~1 to HEAD) to instantly catch which files and functions were modified.

Dependency Analysis : Scans the codebase to see which downstream functions depend on the changed code.

AI & Test Intelligence : Evaluates risks to help prevent unexpected pipeline errors and bugs.

Interactive Dashboard : Uses a clean Streamlit interface so users can easily view impact metrics, seed nodes, and evidence.
demo_repo/ecommerce/ : A built-in sample repository used for testing and demonstrating the tool out-of-the-box.

src/codeimpact/ : The core backend engine containing the logic, parsers, and dependency calculators.

ui/: Houses the user-facing Streamlit dashboard (dashboard.py) that renders the web interface.

requirements.txt: Lists all the necessary Python packages (like Streamlit and GitPython) required for the app to run.
