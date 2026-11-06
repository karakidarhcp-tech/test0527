"""HTML テンプレートから PDF を作る（WeasyPrint）"""
from django.conf import settings
from django.template.loader import render_to_string


def render_pdf(template_name, context):
    from weasyprint import HTML

    html = render_to_string(template_name, context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
