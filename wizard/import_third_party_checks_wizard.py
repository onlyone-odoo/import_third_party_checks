# import_third_party_checks/wizard/import_third_party_checks_wizard.py
import io
import base64
import logging
from datetime import date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)  # Logger para depurar

try:
    import openpyxl
except ImportError:
    _logger.warning("openpyxl not installed.")


class ImportThirdPartyChecksWizard(models.TransientModel):
    _name = "import.third.party.checks.wizard"
    _description = "Wizard to import third party checks from Excel"

    journal_id = fields.Many2one("account.journal", required=True, string="Journal")
    payment_method_line_id = fields.Many2one(
        comodel_name="account.payment.method.line",
        string="Payment Method",
        domain="[]",
        required=True,
    )
    available_payment_method_ids = fields.Many2many(
        comodel_name="account.payment.method.line",
        string="Available Payment Methods",
        compute="_compute_available_payment_method_ids",
        store=False,
    )

    @api.depends("journal_id")
    def _compute_available_payment_method_ids(self):
        for wizard in self:
            if wizard.journal_id:
                # Buscar todas las líneas de métodos de pago asociadas al journal_id
                wizard.available_payment_method_ids = self.env[
                    "account.payment.method.line"
                ].search([("journal_id", "=", wizard.journal_id.id)])
            else:
                # Asignar un conjunto vacío si no hay journal_id seleccionado
                wizard.available_payment_method_ids = self.env[
                    "account.payment.method.line"
                ]

    default_date = fields.Date(string="Default Payment Date")
    file_data = fields.Binary(string="File (Excel)")
    file_name = fields.Char(string="File Name")

    def action_import(self):
        if not self.file_data:
            return

        today_date = date.today()
        file_stream = io.BytesIO(base64.b64decode(self.file_data))

        wb = openpyxl.load_workbook(
            file_stream,
            data_only=True,
            read_only=True,
        )
        sheet = wb.active

        row_index = 0
        for row in sheet.iter_rows(values_only=True):
            row_index += 1
            if row_index == 1:  # Saltear el encabezado
                continue

            partner_name = row[0]
            amount = row[1]
            currency_code = row[2]
            ref = row[3]
            check_number = row[4]
            check_payment_date = row[5]
            bank_name = row[6]

            _logger.info(f"Processing row {row_index}: {row}")

            partner_id = False
            if partner_name:
                partner = self.env["res.partner"].search(
                    [("name", "=", partner_name)], limit=1
                )
                if partner:
                    _logger.info(f"Found partner '{partner_name}' with ID {partner.id}")
                    partner_id = partner.id
                else:
                    _logger.warning(
                        f"Partner '{partner_name}' not found, defaulting to ID 1"
                    )
                    partner_id = 1

            currency_id = self.env.company.currency_id.id
            if currency_code:
                currency = self.env["res.currency"].search(
                    [("name", "=", currency_code)], limit=1
                )
                if currency:
                    _logger.info(
                        f"Found currency '{currency_code}' with ID {currency.id}"
                    )
                    currency_id = currency.id
                else:
                    _logger.warning(
                        f"Currency '{currency_code}' not found, defaulting to company currency"
                    )

            bank_id = False
            if bank_name:
                bank = self.env["res.bank"].search(
                    [("name", "ilike", f"%{bank_name}%")], limit=1
                )
                if bank:
                    _logger.info(f"Found bank '{bank_name}' with ID {bank.id}")
                    bank_id = bank.id
                else:
                    _logger.warning(f"Bank '{bank_name}' not found")

            if not amount:
                _logger.warning(f"Skipping row {row_index} due to missing amount")
                continue

            payment_date = (self.default_date or today_date).isoformat()
            if check_payment_date:
                payment_date = check_payment_date.isoformat()

            receiptbook = self.env["account.payment.receiptbook"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("partner_type", "=", "customer"),
                ],
                limit=1,
            )
            _logger.info(
                f"Using receiptbook ID {receiptbook.id if receiptbook else 'None'}"
            )

            payment_group_vals = {
                "partner_id": partner_id,
                "company_id": self.env.company.id,
                "payment_date": today_date,  # O usa payment_date si deseas
                "receiptbook_id": receiptbook.id if receiptbook else False,
                "communication": ref if ref else False,
                "partner_type": "customer",
            }
            _logger.info(f"Creating payment group with values: {payment_group_vals}")
            payment_group = self.env["account.payment.group"].create(payment_group_vals)

            payment_vals = {
                "payment_group_id": payment_group.id,
                "partner_id": partner_id,
                "amount": amount,
                "currency_id": currency_id,
                "date": today_date,  # O usa payment_date si deseas
                "journal_id": self.journal_id.id,
                "payment_method_line_id": self.payment_method_line_id.id
                if self.payment_method_line_id
                else False,
                "payment_type": "inbound",
                "ref": ref if ref else False,
                "l10n_latam_check_number": check_number,
                "l10n_latam_check_payment_date": payment_date,
            }
            if bank_id:
                payment_vals["l10n_latam_check_bank_id"] = bank_id

            _logger.info(f"Creating payment with values: {payment_vals}")
            payment = self.env["account.payment"].create(payment_vals)
            # validar el payment_group
            payment_group.post()
            # Revertir el asiento contable asociado
            self._revert_payment_move(payment)
        return

    def _revert_payment_move(self, payment):
        """Reversión automática del asiento contable del pago."""
        if not payment.move_id:
            _logger.warning(f"No journal entry found for payment ID {payment.id}")
            return

        _logger.info(f"Reversing journal entry for payment ID {payment.id}")

        # Llama a la acción de reversión
        reversal_wizard = self.env["account.move.reversal"].create(
            {
                "move_ids": [
                    (6, 0, [payment.move_id.id])
                ],  # Relación con el asiento contable
                "date": fields.Date.context_today(self),
                "journal_id": payment.journal_id.id,
                "reason": "Reversal of third-party check import",
            }
        )

        reversal_wizard.reverse_moves()
        _logger.info(f"Reversed journal entry for payment ID {payment.id}")


# si todo sale bien esto deberia dejar cheques sin asientos contables
