# Copyright 2025 Giuseppe Borruso - Dinamiche Aziendali srl
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from io import BytesIO

from lxml import etree

from odoo import api, models, tools
from odoo.exceptions import UserError


class IrAttachmentInherit(models.Model):
    _inherit = "ir.attachment"

    @api.model
    def get_fatturapa_preview_style_name(self):
        """Hook to have a clean inheritance."""
        return "FoglioStileAssoSoftware.xsl"

    def get_xml_string(self):
        # start clickode v19 patch: in Odoo 19 la decodifica EDI e' passata da
        # `ir.attachment` al mixin `account.document.import.mixin` su `account.move`.
        # `_to_files_data` popola `xml_tree` tramite `_get_xml_tree`, che `l10n_it_edi`
        # estende per gestire parser `recover=True` e firma CAdES dei file `.p7m`.
        self.ensure_one()
        move_model = self.env["account.move"]
        file_data = move_model._to_files_data(self)[0]
        if (
            not move_model._is_l10n_it_edi_import_file(file_data)
            or file_data["xml_tree"] is None
        ):
            raise UserError(self.env._("Invalid xml %s.") % self.name)
        return etree.tostring(file_data["xml_tree"])
        # end clickode v19 patch

    def get_fattura_elettronica_preview(self):
        xsl_path = tools.misc.file_path(
            f"l10n_it_edi_extension/data/{self.get_fatturapa_preview_style_name()}"
        )
        xslt = etree.parse(xsl_path)
        xml_string = self.sudo().get_xml_string()
        xml_file = BytesIO(xml_string)
        recovering_parser = etree.XMLParser(recover=True, resolve_entities=False)
        dom = etree.parse(xml_file, parser=recovering_parser)
        transform = etree.XSLT(xslt)
        newdom = transform(dom)
        return etree.tostring(newdom, pretty_print=True, encoding="unicode")
