# pdf_generator.py - ReportLab PDF generation for Empower Reports
import io
import base64
import pandas as pd
import requests
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                  TableStyle, Image)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def get_grade(avg):
    if avg is None:
        return "U"
    try:
        avg = float(avg)
    except Exception:
        return "U"
    if avg >= 90: return "A*"
    elif avg >= 80: return "A"
    elif avg >= 70: return "B"
    elif avg >= 60: return "C"
    elif avg >= 50: return "D"
    elif avg >= 40: return "E"
    return "U"


def generate_pdf_report(student_data, term_data, marks, design,
                         behavior_data=None, decision_data=None, is_vd_report=False):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=0.2*inch, bottomMargin=0.2*inch,
                             leftMargin=0.4*inch, rightMargin=0.4*inch)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                  fontSize=12, textColor=colors.black,
                                  spaceAfter=2, alignment=TA_CENTER, fontName='Helvetica-Bold')
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'],
                                   fontSize=8, textColor=colors.black,
                                   alignment=TA_CENTER, spaceAfter=1)

    # Logo
    if design and design.logo_data:
        try:
            if design.logo_data.startswith('http'):
                logo_bytes = requests.get(design.logo_data, timeout=5).content
            else:
                logo_bytes = base64.b64decode(design.logo_data)
            logo_buf = io.BytesIO(logo_bytes)
            logo = Image(logo_buf, width=1.0*inch, height=1.0*inch)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 0.05*inch))
        except Exception:
            pass

    school_name = (design.school_name if design else "EMPOWER INTERNATIONAL ACADEMY")
    story.append(Paragraph(f"<b>{school_name}</b>", title_style))
    if design and design.school_subtitle:
        story.append(Paragraph(design.school_subtitle, header_style))
    if design and design.school_address:
        story.append(Paragraph(design.school_address, header_style))
    if design and design.school_po_box:
        story.append(Paragraph(design.school_po_box, header_style))

    story.append(Spacer(1, 0.1*inch))
    if is_vd_report:
        story.append(Paragraph(f"<b>MID TERM {term_data['term_number']} REPORT (VD)</b>", title_style))
    else:
        story.append(Paragraph(f"<b>END OF TERM {term_data['term_number']} REPORT</b>", title_style))
    story.append(Spacer(1, 0.1*inch))

    # Student Info Table
    student_info = [
        ['NAME:', student_data.get('name',''), 'REG. NO:', student_data.get('registration_number','')],
        ['CLASS:', student_data.get('class_name',''), 'YEAR:', f"{term_data['year']} - TERM {term_data['term_number']}"]
    ]
    stbl = Table(student_info, colWidths=[0.8*inch, 2.2*inch, 0.8*inch, 2.2*inch])
    stbl.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(stbl)
    story.append(Spacer(1, 0.1*inch))

    # Results Table
    if is_vd_report:
        results_data = [['SUBJECTS', 'MOT', 'GRADE', 'Comment', 'Teacher']]
        if marks is not None and not marks.empty:
            for _, row in marks.iterrows():
                mot = float(row.get('midterm_out_of_20') or 0)
                mot_scaled = round((mot / 20.0) * 100.0, 1) if mot else 0.0
                grade = get_grade(mot_scaled)
                teacher = row.get('teacher_name') or ''
                comment = row.get('comment') or ''
                results_data.append([
                    row['subject'],
                    f"{mot_scaled:.0f}" if mot else '-',
                    grade, comment, teacher
                ])
        col_w = [1.6*inch, 0.5*inch, 0.5*inch, 1.8*inch, 1.1*inch]
    else:
        results_data = [['SUBJECTS', 'CW/20', 'MOT/20', 'EOT/60', 'TOTAL', 'GR', 'Comment', 'Teacher']]
        if marks is not None and not marks.empty:
            for _, row in marks.iterrows():
                cw = row.get('coursework_out_of_20') or 0
                mt = row.get('midterm_out_of_20') or 0
                et = row.get('endterm_out_of_60') or 0
                total = row.get('total') or 0
                grade = row.get('grade') or get_grade(total)
                teacher = row.get('teacher_name') or ''
                comment = row.get('comment') or ''
                results_data.append([
                    row['subject'],
                    f"{cw:.1f}" if cw else '-',
                    f"{mt:.1f}" if mt else '-',
                    f"{et:.1f}" if et else '-',
                    f"{total:.1f}" if total else '-',
                    grade, comment, teacher
                ])
        col_w = [1.3*inch, 0.55*inch, 0.55*inch, 0.55*inch, 0.55*inch, 0.4*inch, 1.2*inch, 1.0*inch]

    results_table = Table(results_data, colWidths=col_w)
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D3D3D3')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(results_table)
    story.append(Spacer(1, 0.1*inch))

    # Decision Table (if provided)
    if decision_data and not is_vd_report:
        decision_val = decision_data.get('decision', '')
        choices = ['Promoted', 'Repeated', 'Transferred', 'Withdrawn', 'Graduated']
        row1 = ['DECISION:'] + [c for c in choices]
        row2 = [''] + ['✓' if c == decision_val else '' for c in choices]
        dtbl = Table([row1, row2], colWidths=[0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch])
        dtbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D3D3D3')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(dtbl)
        story.append(Spacer(1, 0.1*inch))

    # Grading scale
    grading_horizontal = [
        ['A*', 'A', 'B', 'C', 'D', 'E', 'U'],
        ['90-100', '80-89', '70-79', '60-69', '50-59', '40-49', '0-39']
    ]
    grading_table = Table(grading_horizontal, colWidths=[0.7*inch]*7)
    grading_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(grading_table)
    story.append(Spacer(1, 0.05*inch))

    # Key row
    key_horizontal = [[
        Paragraph('<b>CW</b>', ParagraphStyle('KH', fontSize=8)),
        Paragraph('<b>MOT</b>', ParagraphStyle('KH', fontSize=8)),
        Paragraph('<b>EOT</b>', ParagraphStyle('KH', fontSize=8)),
        Paragraph('<b>GR</b>', ParagraphStyle('KH', fontSize=8)),
    ], [
        Paragraph('Coursework', ParagraphStyle('KV', fontSize=7)),
        Paragraph('Mid of Term Test', ParagraphStyle('KV', fontSize=7)),
        Paragraph('End of Term Exam', ParagraphStyle('KV', fontSize=7)),
        Paragraph('Grade', ParagraphStyle('KV', fontSize=7)),
    ]]
    key_table = Table(key_horizontal, colWidths=[1.2*inch, 1.6*inch, 1.6*inch, 0.8*inch])
    key_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(key_table)
    story.append(Spacer(1, 0.05*inch))

    # Classroom Behavior Table
    story.append(Paragraph("<b>CLASSROOM BEHAVIOR:</b>",
                            ParagraphStyle('BT', fontSize=9, fontName='Helvetica-Bold')))
    story.append(Spacer(1, 0.02*inch))

    behavior_items = [
        ('Punctuality', 'punctuality'),
        ('Attendance', 'attendance'),
        ('Manners', 'manners'),
        ('General Behavior', 'general_behavior'),
        ('Organisation', 'organisational_skills'),
        ('Adherence to Uniform', 'adherence_to_uniform'),
        ('Leadership', 'leadership_skills'),
        ('Commitment to School', 'commitment_to_school'),
        ('Cooperation with Peers', 'cooperation_with_peers'),
        ('Cooperation with Staff', 'cooperation_with_staff'),
        ('Participation', 'participation_in_lessons'),
        ('Homework Completion', 'completion_of_homework'),
    ]
    behavior_data_table = [['', 'Excellent', 'Good', 'Satisfactory', 'Concern']]
    for item_label, field_name in behavior_items:
        row = [item_label]
        rating = None
        if behavior_data:
            rating = (behavior_data.get(field_name) or
                      behavior_data.get(item_label) or
                      behavior_data.get(item_label.lower().replace(' ', '_')))
        if rating == 'Excellent':
            row.extend(['✓', '', '', ''])
        elif rating == 'Good':
            row.extend(['', '✓', '', ''])
        elif rating == 'Satisfactory':
            row.extend(['', '', '✓', ''])
        elif rating == 'Cause of Concern':
            row.extend(['', '', '', '✓'])
        else:
            row.extend(['', '', '', ''])
        behavior_data_table.append(row)

    behavior_table = Table(behavior_data_table, colWidths=[1.6*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch])
    behavior_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D3D3D3')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(behavior_table)
    story.append(Spacer(1, 0.1*inch))

    # Signatures
    next_term = term_data.get('next_term_begins', '_______________')
    sig_data = [
        [f"The next term begins on: {next_term}", ''],
        ['', ''],
        ["Class Teacher's signature: _______________________",
         "Principal's signature: _______________________"]
    ]
    sig_table = Table(sig_data, colWidths=[3.0*inch, 3.0*inch])
    sig_table.setStyle(TableStyle([
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,2), (-1,2), 8),
    ]))
    story.append(sig_table)

    # Footer
    if design and design.report_footer:
        story.append(Spacer(1, 0.05*inch))
        story.append(Paragraph(design.report_footer, header_style))

    doc.build(story)
    return buffer.getvalue()


def generate_discipline_pdf(student_data, reports_df, design):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=0.3*inch, bottomMargin=0.3*inch,
                             leftMargin=0.4*inch, rightMargin=0.4*inch)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'],
                                  fontSize=14, alignment=TA_CENTER, fontName='Helvetica-Bold')
    header_style = ParagraphStyle('Header', parent=styles['Normal'],
                                   fontSize=9, alignment=TA_CENTER)

    if design and design.logo_data:
        try:
            if design.logo_data.startswith('http'):
                logo_bytes = requests.get(design.logo_data, timeout=5).content
            else:
                logo_bytes = base64.b64decode(design.logo_data)
            logo_img = Image(io.BytesIO(logo_bytes), width=0.9*inch, height=0.9*inch)
            logo_img.hAlign = 'CENTER'
            story.append(logo_img)
            story.append(Spacer(1, 0.05*inch))
        except Exception:
            pass

    school_name = (design.school_name if design else "EMPOWER INTERNATIONAL ACADEMY")
    story.append(Paragraph(f"<b>{school_name}</b>", title_style))
    if design and design.school_address:
        story.append(Paragraph(design.school_address, header_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>Discipline Report Summary</b>",
                            ParagraphStyle('ST', parent=styles['Heading2'],
                                           alignment=TA_CENTER, fontSize=11)))
    story.append(Spacer(1, 0.08*inch))

    from datetime import datetime as dt
    student_info = [
        ['Name:', student_data.get('name',''), 'Class:', student_data.get('class_name','')],
        ['Reg No:', student_data.get('registration_number',''),
         'Generated:', dt.now().strftime('%Y-%m-%d')]
    ]
    stbl = Table(student_info, colWidths=[0.8*inch, 2.6*inch, 0.8*inch, 2.6*inch])
    stbl.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(stbl)
    story.append(Spacer(1, 0.1*inch))

    if reports_df is None or (hasattr(reports_df, 'empty') and reports_df.empty):
        story.append(Paragraph('No discipline reports available.', styles['Normal']))
    else:
        tbl_data = [['Date', 'Type', 'Description', 'Action Taken', 'Status', 'Admin Notes']]
        for _, r in reports_df.iterrows():
            desc = Paragraph((r.get('description') or '')[:300], ParagraphStyle('Sm', fontSize=8))
            action = Paragraph((r.get('action_taken') or '')[:200], ParagraphStyle('Sm', fontSize=8))
            notes = Paragraph((r.get('admin_notes') or '')[:200], ParagraphStyle('Sm', fontSize=8))
            tbl_data.append([
                r.get('incident_date') or '',
                r.get('incident_type') or '',
                desc, action,
                r.get('status') or '',
                notes,
            ])
        colw = [1.0*inch, 1.0*inch, 2.2*inch, 2.0*inch, 0.7*inch, 1.0*inch]
        rpt_table = Table(tbl_data, colWidths=colw, repeatRows=1)
        rpt_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.4, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F2F2F2')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(rpt_table)

    story.append(Spacer(1, 0.1*inch))
    if design and design.report_footer:
        story.append(Paragraph(design.report_footer, ParagraphStyle('Footer', fontSize=8, alignment=TA_CENTER)))

    doc.build(story)
    return buffer.getvalue()
