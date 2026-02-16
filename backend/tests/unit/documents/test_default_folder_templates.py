from unittest import TestCase

from apps.documents.services.folder_template.default_templates import get_default_folder_templates


class TestDefaultFolderTemplates(TestCase):
    def test_default_folder_templates_shape(self):
        templates = get_default_folder_templates()
        self.assertTrue(len(templates) >= 1)
        for t in templates:
            self.assertIn("name", t)
            self.assertIn("template_type", t)
            self.assertIn("structure", t)
            self.assertIn("is_default", t)
            self.assertIn("is_active", t)

