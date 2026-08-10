# Copyright 2025 Giuseppe Borruso - Dinamiche Aziendali srl
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import logging
import os
import zipfile

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EInvoiceImportFileWizard(models.TransientModel):
    _name = "l10n_it_edi.import_file_wizard"
    _description = "E-invoice Import Files Wizard"

    l10n_it_edi_attachment = fields.Binary()
    l10n_it_edi_attachment_filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        company = self.env.company
        zip_binary = base64.b64decode(self.l10n_it_edi_attachment)
        zip_io = io.BytesIO(zip_binary)
        moves = self.env["account.move"]

        with zipfile.ZipFile(zip_io, "r") as zip_ref:
            for member in zip_ref.infolist():
                if not member.is_dir():
                    with zip_ref.open(member) as file:
                        filename = os.path.basename(member.filename)
                        attachment_model = (
                            self.env["ir.attachment"].sudo().with_company(company)
                        )
                        existing_attachment = attachment_model.search_count(
                            [
                                ("name", "=", filename),
                                ("res_model", "=", "account.move"),
                                ("res_field", "=", "l10n_it_edi_attachment_file"),
                                ("company_id", "=", company.id),
                            ],
                            limit=1,
                        )

                        if existing_attachment:
                            message = f"E-invoice already exists: {filename}"
                            _logger.warning(message)
                            raise UserError(self.env._(message))

                        content = file.read()
                        attachment = attachment_model.create(
                            {
                                "name": filename,
                                "raw": content,
                                "type": "binary",
                            }
                        )

                        # start clickode v19 patch: API di import EDI spostata
                        # da `ir.attachment` a `account.document.import.mixin`.
                        move_model = self.env["account.move"].with_company(company)
                        file_data = move_model._to_files_data(attachment)[0]
                        if (
                            not move_model._is_l10n_it_edi_import_file(file_data)
                            or file_data["xml_tree"] is None
                        ):
                            _logger.info(f"Skipping {filename}, not an XML/P7M file")
                            attachment.unlink()
                            continue

                        # `_unwrap_attachment` crea un ir.attachment per ogni
                        # FatturaElettronicaBody oltre il primo.
                        files_data = [
                            file_data,
                            *move_model._unwrap_attachment(file_data),
                        ]
                        for move_file_data in files_data:
                            move = move_model.create({})
                            move_file_data["attachment"].write(
                                {
                                    "res_model": "account.move",
                                    "res_id": move.id,
                                    "res_field": "l10n_it_edi_attachment_file",
                                }
                            )
                            # come il percorso SdI nativo
                            # (l10n_it_edi._l10n_it_edi_process_downloads_attachments)
                            move.l10n_it_edi_attachment_name = move_file_data["name"]

                            move.with_context(
                                account_predictive_bills_disable_prediction=True,
                                no_new_invoice=True,
                            ).message_post(
                                attachment_ids=move_file_data["attachment"].ids
                            )

                            move._l10n_it_edi_import_invoice(move, move_file_data, True)
                            moves |= move
                        # end clickode v19 patch

        return {
            "view_type": "form",
            "name": "E-invoices",
            "view_mode": "list,form",
            "res_model": "account.move",
            "type": "ir.actions.act_window",
            "domain": [("id", "in", moves.ids)],
        }
