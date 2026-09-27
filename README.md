# CodeImpact

AI-Powered Code Change Impact & Test Intelligence.

#  CodeImpact

## Overview

CodeImpact is a developer tool that analyzes changes made to a Python repository and identifies the potential impact of those changes.

The project combines **Git analysis, Python AST analysis, dependency analysis, test analysis, and AI-assisted reasoning** to help developers understand what may be affected when code changes.

The results are presented through an interactive **Streamlit dashboard**.

---

## Project Objectives

* Analyze changes between Git commits
* Identify changed files and functions
* Trace dependencies across the codebase
* Identify potentially impacted components
* Find relevant tests for the affected code
* Execute and evaluate tests
* Generate AI-assisted explanations of the impact

---

## Technologies / Concepts Used

* Python
* Streamlit
* Git
* Python AST
* Static Code Analysis
* Dependency Analysis
* Test Impact Analysis
* Automated Test Execution
* AI / LLM

---

## Project Files

| **Component**       | **Description**                                       |
| ------------------- | ----------------------------------------------------- |
| `dashboard.py`      | Streamlit interface for CodeImpact                    |
| `pipeline.py`       | Coordinates the analysis workflow                     |
| `git_analyzer.py`   | Analyzes Git changes and identifies changed functions |
| `schemas.py`        | Defines structured analysis results                   |
| Dependency Analysis | Identifies relationships between code components      |
| Impact Analysis     | Determines potentially affected components            |
| Test Analysis       | Identifies and evaluates relevant tests               |

---

## Analysis Workflow

```text
Git Changes
     ↓
Changed Files & Functions
     ↓
Dependency Analysis
     ↓
Impact Analysis
     ↓
Relevant Tests
     ↓
Test Execution
     ↓
Evaluation
     ↓
AI Explanation
```

---

## Key Insights

### Git Change Analysis

CodeImpact analyzes the difference between a base commit and target commit to identify modified files, changed line ranges, and affected Python functions.

The default commit comparison is:

```text
HEAD~1 → HEAD
```

### Function-Level Analysis

Python AST parsing is used to connect changed lines with the functions they belong to.

This allows CodeImpact to analyze changes at the function level rather than only at the file level.

### Dependency-Based Impact

A change in one function can affect other components that depend on it.

CodeImpact uses dependency relationships to identify potentially affected areas beyond the directly modified code.

### Test Impact Analysis

Potentially impacted components are connected to relevant tests.

This creates a relationship between:

```text
Changed Code
     ↓
Impacted Code
     ↓
Relevant Tests
```

### Test Evaluation

Relevant tests can be executed and their results analyzed to compare the predicted impact with the observed behavior.

### AI-Assisted Reasoning

AI is used to make the analysis easier to understand by providing explanations of the detected impact and relationships.

---

## Results

CodeImpact produces a structured impact report containing information such as:

| **Result**          | **Description**                               |
| ------------------- | --------------------------------------------- |
| Changed Files       | Files modified between the selected commits   |
| Changed Functions   | Functions associated with the changed lines   |
| Git Diff            | Details of the code changes                   |
| Impacted Components | Components potentially affected by the change |
| Relevant Tests      | Tests related to the impacted code            |
| Test Results        | Results from test execution                   |
| Evaluation          | Analysis of predicted and observed impact     |
| AI Reasoning        | Explanation of the detected impact            |

---

## Learning Outcome

This project provided practical experience in **Git-based code analysis, Python AST parsing, dependency analysis, test impact analysis, automated testing, Streamlit development, and AI-assisted software engineering**.

It also demonstrated how static analysis, dependency relationships, and test results can be combined to understand the potential impact of software changes.

---

## Hackathon Value

CodeImpact addresses a practical software-engineering problem: understanding the consequences of a code change without manually tracing the entire codebase.

By connecting **code changes, dependencies, relevant tests, test results, and AI reasoning**, CodeImpact provides developers with a unified view of the potential impact of their changes.

---

## Future Enhancements

* Support for additional programming languages
* More test frameworks
* Improved dependency analysis
* GitHub Pull Request integration
* CI/CD integration
* Sandboxed test execution
* Enhanced AI-assisted reasoning

---

## Acknowledgement

CodeImpact was developed as a hackathon project to explore how **AI and static code analysis** can be combined to improve software development and testing workflows.

---

## Author

**CodeImpact Team**

AI-Powered Code Change Impact & Test Intelligence
