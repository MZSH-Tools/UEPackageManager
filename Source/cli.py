from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config_store import ProjectConfigStore
from .models import CONFIGURATIONS, CopyRule
from .packager import PackageRunner, build_command, detect_engine_root, validate_copy_rules


def _add_project_argument(parser: argparse.ArgumentParser, default_root: Path | None) -> None:
    parser.add_argument(
        "--project-root", type=Path, default=default_root, required=default_root is None,
        help="包含 .uproject 的项目目录",
    )


def create_parser(default_root: Path | None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UE 项目打包与附加文件部署工具")
    parser.add_argument("--version", action="version", version="UEPackageManager 2.1.1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    show = subparsers.add_parser("config-show", help="显示当前项目的本地配置")
    _add_project_argument(show, default_root)
    configure = subparsers.add_parser("configure", help="更新当前项目的本地配置")
    _add_project_argument(configure, default_root)
    configure.add_argument("--engine-root")
    configure.add_argument("--output")
    configure.add_argument("--configuration", choices=CONFIGURATIONS)
    copy_list = subparsers.add_parser("copy-list", help="列出当前项目的附加复制规则")
    _add_project_argument(copy_list, default_root)
    copy_add = subparsers.add_parser("copy-add", help="添加当前项目的附加文件或目录")
    _add_project_argument(copy_add, default_root)
    copy_add.add_argument("--source", required=True)
    copy_add.add_argument("--target-directory", default=".")
    copy_add.add_argument(
        "--ignore", action="append", default=[],
        help="递归忽略任意层级中匹配的文件或文件夹名称，可重复指定并支持 *、?",
    )
    copy_remove = subparsers.add_parser("copy-remove", help="按序号删除当前项目的附加复制规则")
    _add_project_argument(copy_remove, default_root)
    copy_remove.add_argument("--index", type=int, required=True)
    validate = subparsers.add_parser("validate", help="验证配置并显示 UAT 命令")
    _add_project_argument(validate, default_root)
    package = subparsers.add_parser("package", help="执行 UE 打包")
    _add_project_argument(package, default_root)
    package.add_argument("--configuration", choices=CONFIGURATIONS)
    package.add_argument("--output")
    package.add_argument("--no-copy", action="store_true")
    package.add_argument("--clean-output", action="store_true", help="打包前清理当前输出路径中识别到的旧包")
    package.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str], default_root: Path | None) -> int:
    args = create_parser(default_root).parse_args(argv)
    store = ProjectConfigStore()
    config = store.load(args.project_root)
    if args.command == "config-show":
        print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "configure":
        if args.engine_root is not None:
            config.engine_root = str(Path(args.engine_root).resolve())
        if args.output is not None:
            config.output_directory = str(Path(args.output).resolve())
        if args.configuration is not None:
            config.configuration = args.configuration
        print(store.save(config))
        return 0
    if args.command == "copy-list":
        print(json.dumps([rule.__dict__ for rule in config.copy_rules], ensure_ascii=False, indent=2))
        return 0
    if args.command == "copy-add":
        config.copy_rules.append(CopyRule(args.source, args.target_directory, recursive_ignores=args.ignore))
        validate_copy_rules(config)
        print(store.save(config))
        return 0
    if args.command == "copy-remove":
        if args.index < 0 or args.index >= len(config.copy_rules):
            raise ValueError(f"复制规则序号超出范围：{args.index}")
        del config.copy_rules[args.index]
        print(store.save(config))
        return 0
    if args.command == "validate":
        config.engine_root = str(detect_engine_root(config.root_path, config.engine_root))
        validate_copy_rules(config)
        command, _ = build_command(config)
        print(command)
        return 0
    if args.command == "package":
        if args.configuration:
            config.configuration = args.configuration
        if args.output:
            config.output_directory = str(Path(args.output).resolve())
        config.engine_root = str(detect_engine_root(config.root_path, config.engine_root))
        if not args.no_copy:
            validate_copy_rules(config)
        if args.dry_run:
            command, _ = build_command(config)
            print(command)
            return 0
        store.save(config)
        PackageRunner().run(config, copy_extras=not args.no_copy, clean_output=args.clean_output)
        return 0
    return 2
