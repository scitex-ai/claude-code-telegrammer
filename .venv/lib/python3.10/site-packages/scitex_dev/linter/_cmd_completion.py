"""CLI subcommand: completion — shell tab completion for scitex-linter."""

import os
import sys


def _generate_completion_script(shell: str) -> str:
    """Generate a static completion script for scitex-linter."""
    if shell == "bash":
        return """# scitex-linter tab completion (bash)
_scitex_linter_complete() {
    local cur prev cmds
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmds="check format python rule rules list-python-apis api mcp completion"

    case "$prev" in
        scitex-linter)
            COMPREPLY=( $(compgen -W "$cmds --help --help-recursive --version" -- "$cur") )
            return 0
            ;;
        check)
            COMPREPLY=( $(compgen -W "--json --no-color --severity --category --help" -f -- "$cur") )
            return 0
            ;;
        format)
            COMPREPLY=( $(compgen -W "--check --diff --help" -f -- "$cur") )
            return 0
            ;;
        python)
            COMPREPLY=( $(compgen -W "--strict --help" -f -- "$cur") )
            return 0
            ;;
        rule|rules)
            COMPREPLY=( $(compgen -W "--json --category --severity --help" -- "$cur") )
            return 0
            ;;
        list-python-apis|api)
            COMPREPLY=( $(compgen -W "--json -v --verbose --help" -- "$cur") )
            return 0
            ;;
        mcp)
            COMPREPLY=( $(compgen -W "start list-tools doctor installation --help" -- "$cur") )
            return 0
            ;;
        completion)
            COMPREPLY=( $(compgen -W "install status bash zsh --help" -- "$cur") )
            return 0
            ;;
        --severity)
            COMPREPLY=( $(compgen -W "error warning info" -- "$cur") )
            return 0
            ;;
    esac

    COMPREPLY=( $(compgen -f -- "$cur") )
}
complete -F _scitex_linter_complete scitex-linter"""
    elif shell == "zsh":
        return """# scitex-linter tab completion (zsh)
#compdef scitex-linter

_scitex-linter() {
    local -a commands
    commands=(
        'check:Check Python files for SciTeX pattern compliance'
        'format:Auto-fix SciTeX pattern issues'
        'python:Lint then execute a Python script'
        'rule:List all lint rules'
        'rules:List all lint rules (built-in + plugin)'
        'list-python-apis:List public Python API'
        'api:List public Python API'
        'mcp:MCP server commands'
        'completion:Shell tab completion'
    )

    _arguments -C \\
        '(-h --help)'{-h,--help}'[Show help]' \\
        '(-V --version)'{-V,--version}'[Show version]' \\
        '--help-recursive[Show help for all commands]' \\
        '1:command:->cmd' \\
        '*::arg:->args'

    case $state in
        cmd)
            _describe 'command' commands
            ;;
    esac
}

_scitex-linter "$@" """
    return ""


def register(subparsers) -> None:
    """Register the completion subcommand."""
    p = subparsers.add_parser(
        "completion",
        help="Shell tab completion",
        description="Install or display shell tab completion for scitex-linter.",
    )
    comp_sub = p.add_subparsers(dest="comp_command")

    inst_p = comp_sub.add_parser("install", help="Install completion to shell RC file")
    inst_p.add_argument(
        "--shell",
        choices=["bash", "zsh"],
        help="Shell type (auto-detected if not provided)",
    )
    inst_p.set_defaults(func=_cmd_install)

    stat_p = comp_sub.add_parser("status", help="Check completion installation status")
    stat_p.set_defaults(func=_cmd_status)

    bash_p = comp_sub.add_parser("bash", help="Show bash completion script")
    bash_p.set_defaults(func=lambda args: _cmd_show("bash"))

    zsh_p = comp_sub.add_parser("zsh", help="Show zsh completion script")
    zsh_p.set_defaults(func=lambda args: _cmd_show("zsh"))

    p.set_defaults(func=lambda args: _cmd_default(p, args))


def _cmd_default(parser, args) -> int:
    if not hasattr(args, "comp_command") or args.comp_command is None:
        parser.print_help()
    return 0


def _cmd_show(shell: str) -> int:
    script = _generate_completion_script(shell)
    if script:
        print(script)
        return 0
    print(f"Unsupported shell: {shell}", file=sys.stderr)
    return 1


def _cmd_install(args) -> int:
    shell = args.shell
    if not shell:
        shell_env = os.environ.get("SHELL", "")
        if "zsh" in shell_env:
            shell = "zsh"
        else:
            shell = "bash"

    script = _generate_completion_script(shell)
    if not script:
        print(f"Unsupported shell: {shell}", file=sys.stderr)
        return 1

    rc_file = os.path.expanduser("~/.bashrc" if shell == "bash" else "~/.zshrc")

    if os.path.exists(rc_file):
        with open(rc_file) as f:
            if "scitex-linter tab completion" in f.read():
                print(f"Completion already installed in {rc_file}")
                return 0

    with open(rc_file, "a") as f:
        f.write(f"\n{script}\n")

    print(f"Completion installed in {rc_file}")
    print(f"Reload with: source {rc_file}")
    return 0


def _cmd_status(args) -> int:
    shell_env = os.environ.get("SHELL", "")
    shell = "zsh" if "zsh" in shell_env else "bash"
    rc_file = os.path.expanduser("~/.bashrc" if shell == "bash" else "~/.zshrc")

    installed = False
    if os.path.exists(rc_file):
        with open(rc_file) as f:
            if "scitex-linter tab completion" in f.read():
                installed = True

    status = "installed" if installed else "not installed"
    print(f"Shell:  {shell}")
    print(f"RC:     {rc_file}")
    print(f"Status: {status}")

    if not installed:
        print("\nInstall with: scitex-linter completion install")

    return 0
