# pylint: disable=missing-module-docstring,pointless-statement
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Import third party checks",
    "summary": """
        creates a wizard to import third party checks includding an automation to reverse the account.moves created by the account_payment_group module
        This will be usefull in case of new odoo implementations with old third party checks """,
    "author": "Be OnlyOne",
    "maintainers": ["onlyone-odoo"],
    "website": "https://onlyone.odoo.com/",
    "license": "AGPL-3",
    "category": "Technical Settings",
    "version": "17.0.1.0.0",
    "development_status": "Production/Stable",
    "external_dependencies": {
        "python": [],
        "bin": [],
    },
    # any module necessary for this one to work correctly
    "depends": [
        "base",
        "account",
        "account_payment_group",
        "l10n_latam_check",  # Asegurate de que este sea el nombre correcto
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/import_third_party_checks_wizard_view.xml",
    ],
    "installable": True,
    "application": False,
}
