# import_third_party_checks/wizard/import_third_party_checks_wizard.py
import base64
import logging
from odoo import api, fields, models

try:
    import openpyxl
except ImportError:
    logging.getLogger(__name__).warning("openpyxl not installed.")


class ImportThirdPartyChecksWizard(models.TransientModel):
    _name = "import.third.party.checks.wizard"
    _description = "Wizard to import third party checks from Excel"

    journal_id = fields.Many2one("account.journal", required=True, string="Journal")
    # Campo "payment_method_line_id" apuntando a account.payment.method.line
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('id', 'in', available_payment_method_line_ids)]",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},  # si tu wizard tuviese estado
    )
    # Se define este M2M para calcular los métodos de pago disponibles
    available_payment_method_line_ids = fields.Many2many(
        "account.payment.method.line",
        compute="_compute_available_payment_method_line_ids",
        store=False,
    )

    @api.depends("journal_id")
    def _compute_available_payment_method_line_ids(self):
        for wizard in self:
            if wizard.journal_id:
                wizard.available_payment_method_line_ids = (
                    wizard.journal_id.payment_method_line_ids
                )
            else:
                wizard.available_payment_method_line_ids = self.env[
                    "account.payment.method.line"
                ].browse([])

    default_date = fields.Date(string="Default Payment Date")
    file_data = fields.Binary(string="File (Excel)")
    file_name = fields.Char(string="File Name")

    def action_import(self):
        if not self.file_data:
            return
        date = today()
        wb = openpyxl.load_workbook(
            filename=False,
            data_only=True,
            read_only=True,
            file_contents=base64.b64decode(self.file_data),
        )
        sheet = wb.active

        # Asumiendo que la primera fila es encabezado
        # Columnas esperadas:
        # A: Cliente (partner_id -> name o algo para buscar?),
        # B: Importe (amount),
        # C: Moneda (currency_id -> code?),
        # D: Referencia (ref) (opcional),
        # E: Numero de cheque (l10n_latam_check_number),
        # F: Fecha de Pago (l10n_latam_check_payment_date),
        # G: Banco (l10n_latam_check_bank_id -> name?)
        row_index = 0
        for row in sheet.iter_rows(values_only=True):
            row_index += 1
            if row_index == 1:
                continue  # skip header

            partner_name = row[0]
            amount = row[1]
            currency_code = row[2]
            ref = row[3]
            check_number = row[4]
            check_payment_date = row[5]
            bank_name = row[6]

            partner_id = False
            if partner_name:
                partner = self.env["res.partner"].search(
                    [("name", "like", partner_name)], limit=1
                )
                if partner:
                    partner_id = partner.id
                else:
                    partner_id = 1

            currency_id = (self.env.company.currency_id.id,)
            if currency_code:
                currency = self.env["res.currency"].search(
                    [("name", "=", currency_code)], limit=1
                )
                if currency:
                    currency_id = currency.id

            bank_id = False
            if bank_name:
                bank = self.env["res.bank"].search(
                    [("name", "like", bank_name)], limit=1
                )
                if bank:
                    bank_id = bank.id

            if not amount:
                continue  # Saltamos si faltan datos esenciales

            payment_date = self.default_date
            if check_payment_date:
                # Si en el excel hay una fecha de pago, usarla
                payment_date = check_payment_date

            receiptbook = self.env["account.payment.receiptbook"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("partner_type", "=", "customer"),
                ],
                limit=1,
            )

            payment_group_vals = {
                "partner_id": partner_id,
                "company_id": self.env.company.id,
                "payment_date": date,
                "receiptbook_id": receiptbook.id if receiptbook else False,
                "ref": ref if ref else False,
            }
            payment_group = self.env["account.payment.group"].create(payment_group_vals)

            payment_vals = {
                "payment_group_id": payment_group.id,
                "partner_id": partner_id,
                "amount": amount,
                "currency_id": currency_id,
                "date": date,
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

            self.env["account.payment"].create(payment_vals)
        return
