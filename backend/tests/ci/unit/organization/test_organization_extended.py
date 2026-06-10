"""Extended tests for organization services - team_service, dto_assemblers, lawyer_import."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.organization.services.team_service import TeamService


class TestTeamService:
    def test_import(self):
        assert TeamService is not None

    def test_validate_team_type_valid(self):
        from apps.organization.models import TeamType

        service = TeamService()
        # Should not raise for valid team types
        for valid_type in TeamType.values:
            service._validate_team_type(valid_type)

    def test_validate_team_type_invalid(self):
        from apps.core.exceptions import ValidationException

        service = TeamService()
        with pytest.raises(ValidationException):
            service._validate_team_type("invalid_type")


class TestDtoAssemblers:
    def test_import(self):
        from apps.organization.services.dto_assemblers import LawyerDtoAssembler, LawFirmDtoAssembler

        assert LawyerDtoAssembler is not None
        assert LawFirmDtoAssembler is not None

    def test_lawyer_dto_assembler(self):
        from apps.organization.services.dto_assemblers import LawyerDtoAssembler

        assembler = LawyerDtoAssembler()
        assert callable(assembler.to_dto)

    def test_lawfirm_dto_assembler(self):
        from apps.organization.services.dto_assemblers import LawFirmDtoAssembler

        assembler = LawFirmDtoAssembler()
        assert callable(assembler.to_dto)


class TestOrganizationServiceAdapter:
    def test_import(self):
        from apps.organization.services import organization_service_adapter

        assert organization_service_adapter is not None


class TestLawyerImportService:
    def test_import(self):
        from apps.organization.services import lawyer_import_service

        assert lawyer_import_service is not None


class TestLawyerResolveService:
    def test_import(self):
        from apps.organization.services import lawyer_resolve_service

        assert lawyer_resolve_service is not None


class TestOrganizationWiring:
    def test_import(self):
        from apps.organization.services import wiring

        assert wiring is not None


class TestOrganizationModels:
    def test_team_type_values(self):
        from apps.organization.models import TeamType

        assert len(TeamType.values) > 0
