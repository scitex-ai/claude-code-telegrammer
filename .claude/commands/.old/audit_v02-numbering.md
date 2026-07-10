## Audit

Is everything clean and professional? For example:

- [ ] Pyproject.toml
  - [ ] This is the place where first author is credited. For me, use:
    - [ ] Yusuke Watanabe
    - [ ] ywatanabe@scitex.ai

- [ ] Documents
  - [ ] Organized, up-to-date, not redundant, necessary and sufficient

- [ ] Shell Script
  - [ ] Have argparser, usage command, help option

- [ ] Python API
  - [ ] Internal code are not exposed to users, minimizing APIs for better user experience

- [ ] CLI commands
  - [ ] No original logics - always use Python or shell logics as is
  - [ ] -h | --help option must be available all for all commands
  - [ ] --help-recursive option must be available for all commands with children
  - [ ] Ensure standardized naming
  - [ ] Intuitive, organized
  - [ ] Cli command is equipped with tab completion
    
- [ ] HTTP Service API
  - [ ] No original logics - always delegate to CLI commands

- [ ] MCP Service API
  - [ ] No original logics - always delegate to CLI commands
  - [ ] What AI agent called must be always reproducible by humans with the corresponding CLI command
  - [ ] Standardized sub-commands:
    $ package-name mcp {start,doctor,installation,list-tools}
    See ~/proj/scitex-code
  - [ ] For MCP server docs (readme, readthedocs), env var/src examples and setup please learn from ~/proj/scitex-audio
    - [ ] /home/ywatanabe/proj/scitex-audio/GITIGNORED/LESSONS.md

- [ ] Tests
  - [ ] Is coverage calculated?
  - [ ] Is coverage sufficient?

- [ ] CI
  - [ ] Is CI correctly setup?
  - [ ] Is the last CI passed? If failed, are they already fixed?

- [ ] Reproducible without developer's memory
  - [ ] See `/no-long-term-memory` command

- [ ] Cleanliness
  - [ ] Is project root clean without unnecessary artifacts?

- [ ] The project will work as expected and documented
  - [ ] Run small experiments for verification if needed 

- [ ] Version consistency
  - [ ] toml, __init__.py, tag, release, pypi and so on

- [ ] PyPI
  - [ ] .github/workflows/publish-pypi.yml
    - [ ] environment pypi
    - [ ] First you need to publish to pypi manually. This is required to configure trusted publisher at pypi.org; project itself is not recognized, displayed otherwise.
    - [ ] So, first check if pypi is serving the package and if not, request to the user for configuration

- [ ] No personal info
  - [ ] If package is designed for publication, do not include my own setups and keep generic tones
  - [ ] .env contents (gitignored), name, email, github should be accepted
  
- [ ] Examples
  - [ ] `./examples` must have demonstrations for main features with numbering like:
    - [ ] `./examples/00_run_all.sh`
    - [ ] `./examples/01_<descriptive-name>.{py,ipynb,sh}`
  - [ ] Artifacts must be saved close place
    - [ ] `./examples/01_<descriptive-name>_out/`
    - [ ] Artifacts should be also included in git (GitHub)

- [ ] Environmental Variables
  - [ ] Safe for name conflict with prefix (e.g., NG: "ENV_NAME", OK: "PROJECT_NAME_ENV_NAME")
  - [ ] PROJECT_NAME_DEBUG_MDOE=1
  - [ ] .env file in project root

- [ ] GitHub About Section
  - [ ] Description, Homepage, and Topics are well-written for the current codebase
  - [ ] Match user expectations and actual implementations
  - [ ] Consider SEO effectiveness as well
    - [ ] Add `scitex` to keywords for scitex ecosystem package

- [ ] SciTeX Brand
  - [ ] Keep consistency in cli commands
  - [ ] Use fastapi and fastmcp when needed
  - [ ] For delegation please check branding changer logics
  - [ ] Do not add ywatanabe@scitex.ai "on footer" of readme
    - [ ] This is new rule to show scitex is not for my project but for the community

  ## SciTeX Package Architecture (3-Layer Cascade)

  See full rules: `~/proj/scitex-dev/docs/MASTER/00_SCITEX_UPSTREAM_AND_DOWNSTREAM_RULES.md`

  ```
  Downstream (apps — standalone, own IO):
    ~/proj/figrecipe, ~/proj/scitex-writer, ~/proj/scitex-clew, ...
        ↑ wraps/cascades via plugin registry
  Middle (shared infrastructure):
    ~/proj/scitex-io, ~/proj/scitex-app, ~/proj/scitex-ui,
    ~/proj/scitex-stats, ~/proj/scitex-audio, ~/proj/scitex-dev
        ↑ integrates/re-exposes (SOC — integration tests ONLY)
  Upstream (orchestration):
    ~/proj/scitex-python (scitex), ~/proj/scitex-cloud
  ```

  ### Key Rules
  - [ ] **Apps work standalone** — no scitex dependency for core functionality
  - [ ] **scitex-io wraps, not replaces** — cascades through plugin registry
  - [ ] **scitex re-exposes only** — no logic, just re-export from middle layer
  - [ ] **Upstream has ONLY integration tests** — unit tests belong downstream
  - [ ] **All 3 interfaces cascade** — Python API, CLI, MCP server same direction
  - [ ] **_AVAILABLE flags** — detect optional deps, provide install instructions
  - [ ] **extras in pyproject.toml** — `pip install figrecipe[scitex]`
  - [ ] **Never reverse imports** — upstream never imports downstream directly

  ### Testing Scope
  - [ ] Downstream (figrecipe): unit tests for own logic
  - [ ] Middle (scitex-io): integration tests for cascade/wrapping
  - [ ] Upstream (scitex): integration tests ONLY for full pipeline

## SciTeX Standalone, Downstream Packages
- [ ] Confirm the original, orchestrate scitex package (~/proj/scitex-python) works as before
- [ ] Ensure always worked local develop -> origin/develop -> origin/main
  - [ ] pip version starts from v0.1.0
- [ ] SciTeX packages must have python apis (minimal), cli commands, and mcp tools:
  - [ ] $ scitex-xxx --help-recursive (in any depth)
  - [ ] $ scitex-xxx list-python-apis -v|-vv|-vvv
  - [ ] $ scitex-xxx mcp list-tools -v|-vv|-vvv
  - [ ] MCP uses fastmcp and the main scitex package ~/proj/scitex-python correctly delegates to the standalone package without any hard coding
  - [ ] After MCP updated, let me know to reconnect scitex mcp server
- [ ] LICENSE is AGPL v3.0 only
  - [ ] CLA.md and CONTRIBUTING.md placed as well like scitex-python
- [ ] Ensure remote is public
- [ ] Read the Docs implemented correctly
  - [ ] Use `$READTHEDOCS_TOKEN` for API access to RTD
  - [ ] First, push to GitHub with the RTD conifg file and source. 
  - [ ] Then, please let me know. I will configure to trigger RTD build on PR to main
  - [ ] If you can register trusted publisher, please set by yourself
- [ ] Before pushing to origin/develop, please ensure "/audit" passed
- [ ] Ensure README.md follows the same format with https://github.com/ywatanabe1989/scitex-clew/README.md
  - [ ] Ensure that README.md organization is as follows. 
        Note: Add custom sections flexibly
        Note: Use <details>, <summary>, tables, figures effectively
        Note: Figure and Tables need legend like in scientific papers
        Note: Figures must be visible in both dark/light modes
        Note: Ensure icons are correctly git-tracked and pushed
        Note: Acronyms must be spelled out on their first appearance.
    - [ ] Project Title (e.g., `SciTeX Stats`)
    - [ ] Header - Logo, Description, badges, RTD Link, pip install xxx
    - [ ] Problem (scope definition, problem description)
    - [ ] Solution (How <package-name> solves the problem)
    - [ ] No `import scitex as stx`; use `import scitex` instead in READMEs and RTD
    - [ ] Installation
    - [ ] Quick Start
    - [ ] Three Interfaces
      - [ ] Python API
      - [ ] CLI Commands
      - [ ] MCP Server
    - [ ] Part of SciTeX
      - [ ] <package-name> is part of SciTeX. When used in side the orchestrator package `scitex`, synergy between modules can be enjoyed: (revise this sentence based on the package and synergy packages with example code)
      - [ ] If synergy is not expected skip the "When used in ..." section., skip this as the Python API section above will suffice.
      - [ ] The SciTeX ecosystem follows the Four Freedoms for researchers, inspired by [the Free Software Definition](https://www.gnu.org/philosophy/free-sw.en.html):
        - [ ] ...
    - [ ] Footer with scitex icon
- [ ] ./examples implemented
- [ ] ./tests implemented
- [ ] Add `scitex_dev` as dependency in each package's `pyproject.toml`
- [ ] Use `@supports_return_as` decorator:
- [ ] Unified MCP response format across all mounted MCP servers
- [ ] Wire `docs` entry points in all packages


If you find room for improvement, do not hesitate but keep on working the remaining tasks
