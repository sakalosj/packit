# MIT License
#
# Copyright (c) 2018-2019 Red Hat, Inc.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Union

from yaml import safe_load

from ogr.abstract import GitProject
from packit.actions import ActionName
from packit.constants import CONFIG_FILE_NAMES, PROD_DISTGIT_URL
from packit.config.base_config import BaseConfig
from packit.config.job_config import JobConfig, get_from_raw_jobs
from packit.config.sync_files_config import SyncFilesConfig, SyncFilesItem
from packit.exceptions import PackitConfigException, PackitException
from packit.schema import PACKAGE_CONFIG_SCHEMA

logger = logging.getLogger(__name__)


class PackageConfig(BaseConfig):
    """
    Config class for upstream/downstream packages;
    this is the config people put in their repos
    """

    SCHEMA = PACKAGE_CONFIG_SCHEMA

    def __init__(
        self,
        config_file_path: Optional[str] = None,
        specfile_path: Optional[str] = None,
        synced_files: Optional[SyncFilesConfig] = None,
        jobs: Optional[List[JobConfig]] = None,
        dist_git_namespace: str = None,
        upstream_project_url: str = None,  # can be URL or path
        upstream_package_name: str = None,
        downstream_project_url: str = None,
        downstream_package_name: str = None,
        dist_git_base_url: str = None,
        create_tarball_command: List[str] = None,
        current_version_command: List[str] = None,
        actions: Dict[ActionName, Union[str, List[str]]] = None,
        upstream_ref: Optional[str] = None,
        allowed_gpg_keys: Optional[List[str]] = None,
        create_pr: bool = True,
        spec_source_id: str = "Source0",
        upstream_tag_template: str = "{version}",
    ):
        self.config_file_path: Optional[str] = config_file_path
        self.specfile_path: Optional[str] = specfile_path
        self.synced_files: SyncFilesConfig = synced_files or SyncFilesConfig([])
        self.jobs: List[JobConfig] = jobs or []
        self.dist_git_namespace: str = dist_git_namespace or "rpms"
        self.upstream_project_url: Optional[str] = upstream_project_url
        self.upstream_package_name: Optional[str] = upstream_package_name
        # this is generated by us
        self.downstream_package_name: Optional[str] = downstream_package_name
        self.dist_git_base_url: str = dist_git_base_url or PROD_DISTGIT_URL
        self._downstream_project_url: str = downstream_project_url
        # path to a local git clone of the dist-git repo; None means to clone in a tmpdir
        self.dist_git_clone_path: Optional[str] = None
        self.actions = actions or {}
        self.upstream_ref: Optional[str] = upstream_ref
        self.allowed_gpg_keys = allowed_gpg_keys
        self.create_pr: bool = create_pr
        self.spec_source_id: str = spec_source_id

        # command to generate a tarball from the upstream repo
        # uncommitted changes will not be present in the archive
        self.create_tarball_command: List[str] = create_tarball_command
        # command to get current version of the project
        self.current_version_command: List[str] = current_version_command or [
            "git",
            "describe",
            "--tags",
            "--match",
            "*",
        ]
        # template to create an upstream tag name (upstream may use different tagging scheme)
        self.upstream_tag_template = upstream_tag_template

    @property
    def downstream_project_url(self) -> str:
        if not self._downstream_project_url:
            self._downstream_project_url = self.dist_git_package_url
        return self._downstream_project_url

    def __eq__(self, other: object):
        if not isinstance(other, self.__class__):
            return NotImplemented
        logger.debug(f"our configuration:\n{self.__dict__}")
        logger.debug(f"the other configuration:\n{other.__dict__}")
        return (
            self.specfile_path == other.specfile_path
            and self.synced_files == other.synced_files
            and self.jobs == other.jobs
            and self.dist_git_namespace == other.dist_git_namespace
            and self.upstream_project_url == other.upstream_project_url
            and self.upstream_package_name == other.upstream_package_name
            and self.downstream_project_url == other.downstream_project_url
            and self.downstream_package_name == other.downstream_package_name
            and self.dist_git_base_url == other.dist_git_base_url
            and self.current_version_command == other.current_version_command
            and self.create_tarball_command == other.create_tarball_command
            and self.actions == other.actions
            and self.allowed_gpg_keys == other.allowed_gpg_keys
            and self.create_pr == other.create_pr
            and self.spec_source_id == other.spec_source_id
            and self.upstream_tag_template == other.upstream_tag_template
        )

    @property
    def dist_git_package_url(self):
        return (
            f"{self.dist_git_base_url}{self.dist_git_namespace}/"
            f"{self.downstream_package_name}.git"
        )

    @classmethod
    def get_from_dict(
        cls,
        raw_dict: dict,
        config_file_path: str = None,
        repo_name: str = None,
        validate=True,
    ) -> "PackageConfig":
        if validate:
            cls.validate(raw_dict)

        synced_files = raw_dict.get("synced_files", None)
        actions = raw_dict.get("actions", {})

        raw_jobs = raw_dict.get("jobs", None)
        jobs = get_from_raw_jobs(raw_jobs)

        create_tarball_command = raw_dict.get("create_tarball_command", None)
        current_version_command = raw_dict.get("current_version_command", None)

        upstream_package_name = (
            cls.get_deprecated_key(
                raw_dict, "upstream_package_name", "upstream_project_name"
            )
            or cls.get_deprecated_key(
                raw_dict, "upstream_package_name", "upstream_name"
            )
            or repo_name
        )

        upstream_project_url = raw_dict.get("upstream_project_url", None)

        if raw_dict.get("dist_git_url", None):
            logger.warning(
                "dist_git_url is no longer being processed, "
                "it is generated from dist_git_base_url and downstream_package_name"
            )
        downstream_package_name = (
            cls.get_deprecated_key(raw_dict, "downstream_package_name", "package_name")
            or repo_name
        )

        specfile_path = raw_dict.get("specfile_path", None)
        if not specfile_path:
            if downstream_package_name:
                specfile_path = f"{downstream_package_name}.spec"
                logger.info(f"We guess that spec file is at {specfile_path}")
            else:
                # guess it?
                logger.warning("Path to spec file is not set.")

        dist_git_base_url = raw_dict.get("dist_git_base_url")
        dist_git_namespace = raw_dict.get("dist_git_namespace")
        upstream_ref = raw_dict.get("upstream_ref")

        allowed_gpg_keys = raw_dict.get("allowed_gpg_keys")
        create_pr = raw_dict.get("create_pr", True)
        upstream_tag_template = raw_dict.get("upstream_tag_template", "{version}")

        # it can be int as well
        spec_source_id = raw_dict.get("spec_source_id", "Source0")
        try:
            spec_source_id = int(spec_source_id)
        except ValueError:
            # not a number
            pass
        else:
            # is a number!
            spec_source_id = f"Source{spec_source_id}"

        pc = PackageConfig(
            config_file_path=config_file_path,
            specfile_path=specfile_path,
            synced_files=SyncFilesConfig.get_from_dict(synced_files, validate=False),
            actions={ActionName(a): cmd for a, cmd in actions.items()},
            jobs=jobs,
            upstream_package_name=upstream_package_name,
            downstream_package_name=downstream_package_name,
            upstream_project_url=upstream_project_url,
            dist_git_base_url=dist_git_base_url,
            dist_git_namespace=dist_git_namespace,
            create_tarball_command=create_tarball_command,
            current_version_command=current_version_command,
            upstream_ref=upstream_ref,
            allowed_gpg_keys=allowed_gpg_keys,
            create_pr=create_pr,
            spec_source_id=spec_source_id,
            upstream_tag_template=upstream_tag_template,
        )
        return pc

    @staticmethod
    def get_deprecated_key(raw_dict: dict, new_key_name: str, old_key_name: str):
        old = raw_dict.get(old_key_name, None)
        if old:
            logger.warning(
                f"{old_key_name!r} configuration key was renamed to {new_key_name!r},"
                f" please update your configuration file"
            )
        r = raw_dict.get(new_key_name, None)
        if not r:
            # prio: new > old
            r = old
        return r

    def get_all_files_to_sync(self):
        """
        Adds the default files (config file, spec file) to synced files when doing propose-update.
        :return: SyncFilesConfig with default files
        """
        files = self.synced_files.files_to_sync

        if self.specfile_path not in (item.src for item in files):
            files.append(SyncFilesItem(src=self.specfile_path, dest=self.specfile_path))

        if self.config_file_path not in (item.src for item in files):
            files.append(
                SyncFilesItem(src=self.config_file_path, dest=self.config_file_path)
            )

        return SyncFilesConfig(files)


def get_local_package_config(
    *directory,
    repo_name: str = None,
    try_local_dir_first=False,
    try_local_dir_last=False,
) -> PackageConfig:
    """
    :return: local PackageConfig if present
    """
    directories = [Path(config_dir) for config_dir in directory]

    if try_local_dir_first:
        directories.insert(0, Path.cwd())

    if try_local_dir_last:
        directories.append(Path.cwd())

    for config_dir in directories:
        for config_file_name in CONFIG_FILE_NAMES:
            config_file_name_full = config_dir / config_file_name
            if config_file_name_full.is_file():
                logger.debug(f"Local package config found: {config_file_name_full}")
                try:
                    loaded_config = safe_load(open(config_file_name_full))
                except Exception as ex:
                    logger.error(
                        f"Cannot load package config '{config_file_name_full}'."
                    )
                    raise Exception(f"Cannot load package config: {ex}.")
                return parse_loaded_config(
                    loaded_config=loaded_config,
                    config_file_path=str(config_file_name),
                    repo_name=repo_name,
                )

            logger.debug(f"The local config file '{config_file_name_full}' not found.")
    raise PackitConfigException("No packit config found.")


def get_package_config_from_repo(
    sourcegit_project: GitProject, ref: str
) -> Optional[PackageConfig]:
    for config_file_name in CONFIG_FILE_NAMES:
        try:
            config_file_content = sourcegit_project.get_file_content(
                path=config_file_name, ref=ref
            )
            logger.debug(
                f"Found a config file '{config_file_name}' "
                f"on ref '{ref}' "
                f"of the {sourcegit_project.full_repo_name} repository."
            )
        except FileNotFoundError as ex:
            logger.debug(
                f"The config file '{config_file_name}' "
                f"not found on ref '{ref}' "
                f"of the {sourcegit_project.full_repo_name} repository."
                f"{ex!r}"
            )
            continue

        try:
            loaded_config = safe_load(config_file_content)
        except Exception as ex:
            logger.error(f"Cannot load package config '{config_file_name}'.")
            raise PackitException(f"Cannot load package config: {ex}.")
        return parse_loaded_config(
            loaded_config=loaded_config,
            config_file_path=config_file_name,
            repo_name=sourcegit_project.repo,
        )

    logger.warning(
        f"No config file found on ref '{ref}' "
        f"of the {sourcegit_project.full_repo_name} repository."
    )
    return None


def parse_loaded_config(
    loaded_config: dict, config_file_path: str = None, repo_name: str = None
) -> PackageConfig:
    """Tries to parse the config to PackageConfig."""
    logger.debug(f"Package config:\n{json.dumps(loaded_config, indent=4)}")

    try:
        package_config = PackageConfig.get_from_dict(
            raw_dict=loaded_config,
            config_file_path=config_file_path,
            repo_name=repo_name,
            validate=True,
        )
        return package_config
    except Exception as ex:
        logger.error(f"Cannot parse package config. {ex}.")
        raise Exception(f"Cannot parse package config: {ex}.")
