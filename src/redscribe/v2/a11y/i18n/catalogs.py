"""Message catalogs, translation lookup, interpolation, and coverage reports."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.a11y.i18n.locales import fallback_chain, normalize_locale
from redscribe.v2.a11y.models import MessageEntry

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

EN_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "Save",
    "action.cancel": "Cancel",
    "action.delete": "Delete",
    "action.edit": "Edit",
    "action.open": "Open",
    "action.close": "Close",
    "action.create": "Create",
    "action.retry": "Try again",
    "action.apply": "Apply",
    "action.reset": "Reset",
    "action.search": "Search",
    "nav.home": "Home",
    "nav.notes": "Notes",
    "nav.dashboard": "Dashboard",
    "nav.settings": "Settings",
    "nav.help": "Help",
    "nav.graph": "Graph",
    "nav.timeline": "Timeline",
    "nav.trash": "Trash",
    "status.loading": "Loading…",
    "status.ready": "Ready",
    "status.saved": "Saved",
    "status.saving": "Saving…",
    "status.error": "Something went wrong",
    "status.empty": "Nothing here yet",
    "status.offline": "Working offline",
    "a11y.panel.title": "Accessibility",
    "a11y.panel.subtitle": "Review language, contrast, focus, and shortcuts.",
    "a11y.audit.run": "Run accessibility audit",
    "a11y.audit.score": "Accessibility score: {score}",
    "a11y.audit.issues": "{count} issues found",
    "a11y.audit.clean": "No issues found",
    "a11y.contrast.title": "Contrast report",
    "a11y.contrast.ratio": "Contrast ratio {ratio} to 1",
    "a11y.contrast.pass": "Passes {level}",
    "a11y.contrast.fail": "Below {level}",
    "a11y.focus.title": "Focus order",
    "a11y.focus.step": "Step {order}: {label}",
    "a11y.focus.skip_link": "Skip link available",
    "a11y.shortcuts.title": "Keyboard shortcuts",
    "a11y.shortcuts.conflict": "{first} conflicts with {second}",
    "a11y.theme.title": "Theme",
    "a11y.theme.picker": "Choose a theme",
    "a11y.locale.title": "Language",
    "a11y.locale.picker": "Choose a language",
    "a11y.direction": "Text direction",
    "a11y.reduce_motion": "Reduce motion",
    "a11y.high_contrast": "High contrast",
    "a11y.screen_reader_hints": "Screen reader hints",
    "a11y.announce.saved": "Note saved",
    "a11y.announce.deleted": "Note moved to trash",
    "a11y.announce.loaded": "{count} notes loaded",
    "plural.note.one": "{count} note",
    "plural.note.other": "{count} notes",
    "plural.issue.one": "{count} issue",
    "plural.issue.other": "{count} issues",
    "format.date": "Date: {date}",
    "format.number": "Number: {value}",
}

ES_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "Guardar",
    "action.cancel": "Cancelar",
    "action.delete": "Eliminar",
    "action.edit": "Editar",
    "action.open": "Abrir",
    "action.close": "Cerrar",
    "action.create": "Crear",
    "action.retry": "Reintentar",
    "action.apply": "Aplicar",
    "action.reset": "Restablecer",
    "action.search": "Buscar",
    "nav.home": "Inicio",
    "nav.notes": "Notas",
    "nav.dashboard": "Panel",
    "nav.settings": "Ajustes",
    "nav.help": "Ayuda",
    "nav.graph": "Grafo",
    "nav.timeline": "Cronología",
    "nav.trash": "Papelera",
    "status.loading": "Cargando…",
    "status.ready": "Listo",
    "status.saved": "Guardado",
    "status.saving": "Guardando…",
    "status.error": "Algo salió mal",
    "status.empty": "Todavía no hay nada",
    "status.offline": "Trabajando sin conexión",
    "a11y.panel.title": "Accesibilidad",
    "a11y.panel.subtitle": "Revisa idioma, contraste, foco y atajos.",
    "a11y.audit.run": "Ejecutar auditoría de accesibilidad",
    "a11y.audit.score": "Puntuación de accesibilidad: {score}",
    "a11y.audit.issues": "Se encontraron {count} problemas",
    "a11y.audit.clean": "No se encontraron problemas",
    "a11y.contrast.title": "Informe de contraste",
    "a11y.contrast.ratio": "Relación de contraste {ratio} a 1",
    "a11y.contrast.pass": "Cumple {level}",
    "a11y.contrast.fail": "Por debajo de {level}",
    "a11y.focus.title": "Orden de foco",
    "a11y.focus.step": "Paso {order}: {label}",
    "a11y.focus.skip_link": "Enlace de salto disponible",
    "a11y.shortcuts.title": "Atajos de teclado",
    "a11y.shortcuts.conflict": "{first} entra en conflicto con {second}",
    "a11y.theme.title": "Tema",
    "a11y.theme.picker": "Elige un tema",
    "a11y.locale.title": "Idioma",
    "a11y.locale.picker": "Elige un idioma",
    "a11y.direction": "Dirección del texto",
    "a11y.reduce_motion": "Reducir movimiento",
    "a11y.high_contrast": "Alto contraste",
    "a11y.screen_reader_hints": "Pistas para lector de pantalla",
    "a11y.announce.saved": "Nota guardada",
    "a11y.announce.deleted": "Nota movida a la papelera",
    "a11y.announce.loaded": "{count} notas cargadas",
    "plural.note.one": "{count} nota",
    "plural.note.other": "{count} notas",
    "plural.issue.one": "{count} problema",
    "plural.issue.other": "{count} problemas",
    "format.date": "Fecha: {date}",
    "format.number": "Número: {value}",
}

FR_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "Enregistrer",
    "action.cancel": "Annuler",
    "action.delete": "Supprimer",
    "action.edit": "Modifier",
    "action.open": "Ouvrir",
    "action.close": "Fermer",
    "action.create": "Créer",
    "action.retry": "Réessayer",
    "action.apply": "Appliquer",
    "action.reset": "Réinitialiser",
    "action.search": "Rechercher",
    "nav.home": "Accueil",
    "nav.notes": "Notes",
    "nav.dashboard": "Tableau de bord",
    "nav.settings": "Paramètres",
    "nav.help": "Aide",
    "nav.graph": "Graphe",
    "nav.timeline": "Chronologie",
    "nav.trash": "Corbeille",
    "status.loading": "Chargement…",
    "status.ready": "Prêt",
    "status.saved": "Enregistré",
    "status.saving": "Enregistrement…",
    "status.error": "Une erreur est survenue",
    "status.empty": "Rien pour le moment",
    "status.offline": "Travail hors ligne",
    "a11y.panel.title": "Accessibilité",
    "a11y.panel.subtitle": "Vérifiez la langue, le contraste, le focus et les raccourcis.",
    "a11y.audit.run": "Lancer l’audit d’accessibilité",
    "a11y.audit.score": "Score d’accessibilité : {score}",
    "a11y.audit.issues": "{count} problèmes trouvés",
    "a11y.audit.clean": "Aucun problème trouvé",
    "a11y.contrast.title": "Rapport de contraste",
    "a11y.contrast.ratio": "Rapport de contraste {ratio} pour 1",
    "a11y.contrast.pass": "Conforme {level}",
    "a11y.contrast.fail": "Inférieur à {level}",
    "a11y.focus.title": "Ordre de focus",
    "a11y.focus.step": "Étape {order} : {label}",
    "a11y.focus.skip_link": "Lien d’évitement disponible",
    "a11y.shortcuts.title": "Raccourcis clavier",
    "a11y.shortcuts.conflict": "{first} conflite avec {second}",
    "a11y.theme.title": "Thème",
    "a11y.theme.picker": "Choisir un thème",
    "a11y.locale.title": "Langue",
    "a11y.locale.picker": "Choisir une langue",
    "a11y.direction": "Sens du texte",
    "a11y.reduce_motion": "Réduire les animations",
    "a11y.high_contrast": "Contraste élevé",
    "a11y.screen_reader_hints": "Indices pour lecteur d’écran",
    "a11y.announce.saved": "Note enregistrée",
    "a11y.announce.deleted": "Note déplacée dans la corbeille",
    "a11y.announce.loaded": "{count} notes chargées",
    "plural.note.one": "{count} note",
    "plural.note.other": "{count} notes",
    "plural.issue.one": "{count} problème",
    "plural.issue.other": "{count} problèmes",
    "format.date": "Date : {date}",
    "format.number": "Nombre : {value}",
}

DE_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "Speichern",
    "action.cancel": "Abbrechen",
    "action.delete": "Löschen",
    "action.edit": "Bearbeiten",
    "action.open": "Öffnen",
    "action.close": "Schließen",
    "action.create": "Erstellen",
    "action.retry": "Erneut versuchen",
    "action.apply": "Anwenden",
    "action.reset": "Zurücksetzen",
    "action.search": "Suchen",
    "nav.home": "Start",
    "nav.notes": "Notizen",
    "nav.dashboard": "Übersicht",
    "nav.settings": "Einstellungen",
    "nav.help": "Hilfe",
    "nav.graph": "Graph",
    "nav.timeline": "Zeitleiste",
    "nav.trash": "Papierkorb",
    "status.loading": "Wird geladen…",
    "status.ready": "Bereit",
    "status.saved": "Gespeichert",
    "status.saving": "Wird gespeichert…",
    "status.error": "Etwas ist schiefgelaufen",
    "status.empty": "Noch nichts vorhanden",
    "status.offline": "Offline-Arbeit",
    "a11y.panel.title": "Barrierefreiheit",
    "a11y.panel.subtitle": "Sprache, Kontrast, Fokus und Tastenkürzel prüfen.",
    "a11y.audit.run": "Barrierefreiheitsprüfung starten",
    "a11y.audit.score": "Barrierefreiheitswert: {score}",
    "a11y.audit.issues": "{count} Probleme gefunden",
    "a11y.audit.clean": "Keine Probleme gefunden",
    "a11y.contrast.title": "Kontrastbericht",
    "a11y.contrast.ratio": "Kontrastverhältnis {ratio} zu 1",
    "a11y.contrast.pass": "Erfüllt {level}",
    "a11y.contrast.fail": "Unter {level}",
    "a11y.focus.title": "Fokusreihenfolge",
    "a11y.focus.step": "Schritt {order}: {label}",
    "a11y.focus.skip_link": "Sprunglink verfügbar",
    "a11y.shortcuts.title": "Tastenkürzel",
    "a11y.shortcuts.conflict": "{first} steht im Konflikt mit {second}",
    "a11y.theme.title": "Design",
    "a11y.theme.picker": "Design auswählen",
    "a11y.locale.title": "Sprache",
    "a11y.locale.picker": "Sprache auswählen",
    "a11y.direction": "Textrichtung",
    "a11y.reduce_motion": "Bewegung reduzieren",
    "a11y.high_contrast": "Hoher Kontrast",
    "a11y.screen_reader_hints": "Hinweise für Screenreader",
    "a11y.announce.saved": "Notiz gespeichert",
    "a11y.announce.deleted": "Notiz in den Papierkorb verschoben",
    "a11y.announce.loaded": "{count} Notizen geladen",
    "plural.note.one": "{count} Notiz",
    "plural.note.other": "{count} Notizen",
    "plural.issue.one": "{count} Problem",
    "plural.issue.other": "{count} Probleme",
    "format.date": "Datum: {date}",
    "format.number": "Zahl: {value}",
}

AR_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "حفظ",
    "action.cancel": "إلغاء",
    "action.delete": "حذف",
    "action.edit": "تحرير",
    "action.open": "فتح",
    "action.close": "إغلاق",
    "action.create": "إنشاء",
    "action.retry": "إعادة المحاولة",
    "action.apply": "تطبيق",
    "action.reset": "إعادة تعيين",
    "action.search": "بحث",
    "nav.home": "الرئيسية",
    "nav.notes": "الملاحظات",
    "nav.dashboard": "لوحة التحكم",
    "nav.settings": "الإعدادات",
    "nav.help": "المساعدة",
    "nav.graph": "الرسم البياني",
    "nav.timeline": "الجدول الزمني",
    "nav.trash": "المهملات",
    "status.loading": "جارٍ التحميل…",
    "status.ready": "جاهز",
    "status.saved": "تم الحفظ",
    "status.saving": "جارٍ الحفظ…",
    "status.error": "حدث خطأ ما",
    "status.empty": "لا يوجد شيء بعد",
    "status.offline": "العمل دون اتصال",
    "a11y.panel.title": "إمكانية الوصول",
    "a11y.panel.subtitle": "راجع اللغة والتباين والتركيز واختصارات لوحة المفاتيح.",
    "a11y.audit.run": "تشغيل تدقيق إمكانية الوصول",
    "a11y.audit.score": "درجة إمكانية الوصول: {score}",
    "a11y.audit.issues": "تم العثور على {count} مشكلة",
    "a11y.audit.clean": "لم يتم العثور على مشكلات",
    "a11y.contrast.title": "تقرير التباين",
    "a11y.contrast.ratio": "نسبة التباين {ratio} إلى 1",
    "a11y.contrast.pass": "يفي بـ {level}",
    "a11y.contrast.fail": "أقل من {level}",
    "a11y.focus.title": "ترتيب التركيز",
    "a11y.focus.step": "الخطوة {order}: {label}",
    "a11y.focus.skip_link": "رابط التخطي متاح",
    "a11y.shortcuts.title": "اختصارات لوحة المفاتيح",
    "a11y.shortcuts.conflict": "{first} يتعارض مع {second}",
    "a11y.theme.title": "المظهر",
    "a11y.theme.picker": "اختر مظهرًا",
    "a11y.locale.title": "اللغة",
    "a11y.locale.picker": "اختر لغة",
    "a11y.direction": "اتجاه النص",
    "a11y.reduce_motion": "تقليل الحركة",
    "a11y.high_contrast": "تباين عالٍ",
    "a11y.screen_reader_hints": "تلميحات قارئ الشاشة",
    "a11y.announce.saved": "تم حفظ الملاحظة",
    "a11y.announce.deleted": "تم نقل الملاحظة إلى المهملات",
    "a11y.announce.loaded": "تم تحميل {count} ملاحظة",
    "plural.note.one": "ملاحظة واحدة",
    "plural.note.other": "{count} ملاحظات",
    "plural.issue.one": "مشكلة واحدة",
    "plural.issue.other": "{count} مشكلات",
    "format.date": "التاريخ: {date}",
    "format.number": "الرقم: {value}",
}

HE_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "שמור",
    "action.cancel": "ביטול",
    "action.delete": "מחק",
    "action.edit": "ערוך",
    "action.open": "פתח",
    "action.close": "סגור",
    "action.create": "צור",
    "action.retry": "נסה שוב",
    "action.apply": "החל",
    "action.reset": "אפס",
    "action.search": "חיפוש",
    "nav.home": "בית",
    "nav.notes": "הערות",
    "nav.dashboard": "לוח בקרה",
    "nav.settings": "הגדרות",
    "nav.help": "עזרה",
    "nav.graph": "גרף",
    "nav.timeline": "ציר זמן",
    "nav.trash": "אשפה",
    "status.loading": "טוען…",
    "status.ready": "מוכן",
    "status.saved": "נשמר",
    "status.saving": "שומר…",
    "status.error": "משהו השתבש",
    "status.empty": "אין עדיין כלום",
    "status.offline": "עובד ללא חיבור",
    "a11y.panel.title": "נגישות",
    "a11y.panel.subtitle": "בדוק שפה, ניגודיות, מיקוד וקיצורי מקלדת.",
    "a11y.audit.run": "הפעל בדיקת נגישות",
    "a11y.audit.score": "ציון נגישות: {score}",
    "a11y.audit.issues": "נמצאו {count} בעיות",
    "a11y.audit.clean": "לא נמצאו בעיות",
    "a11y.contrast.title": "דוח ניגודיות",
    "a11y.contrast.ratio": "יחס ניגודיות {ratio} ל־1",
    "a11y.contrast.pass": "עומד ב־{level}",
    "a11y.contrast.fail": "מתחת ל־{level}",
    "a11y.focus.title": "סדר מיקוד",
    "a11y.focus.step": "שלב {order}: {label}",
    "a11y.focus.skip_link": "קישור דילוג זמין",
    "a11y.shortcuts.title": "קיצורי מקלדת",
    "a11y.shortcuts.conflict": "{first} מתנגש עם {second}",
    "a11y.theme.title": "ערכת נושא",
    "a11y.theme.picker": "בחר ערכת נושא",
    "a11y.locale.title": "שפה",
    "a11y.locale.picker": "בחר שפה",
    "a11y.direction": "כיוון טקסט",
    "a11y.reduce_motion": "הפחת תנועה",
    "a11y.high_contrast": "ניגודיות גבוהה",
    "a11y.screen_reader_hints": "רמזים לקורא מסך",
    "a11y.announce.saved": "הערה נשמרה",
    "a11y.announce.deleted": "הערה הועברה לאשפה",
    "a11y.announce.loaded": "נטענו {count} הערות",
    "plural.note.one": "הערה אחת",
    "plural.note.other": "{count} הערות",
    "plural.issue.one": "בעיה אחת",
    "plural.issue.other": "{count} בעיות",
    "format.date": "תאריך: {date}",
    "format.number": "מספר: {value}",
}

JA_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "保存",
    "action.cancel": "キャンセル",
    "action.delete": "削除",
    "action.edit": "編集",
    "action.open": "開く",
    "action.close": "閉じる",
    "action.create": "作成",
    "action.retry": "再試行",
    "action.apply": "適用",
    "action.reset": "リセット",
    "action.search": "検索",
    "nav.home": "ホーム",
    "nav.notes": "ノート",
    "nav.dashboard": "ダッシュボード",
    "nav.settings": "設定",
    "nav.help": "ヘルプ",
    "nav.graph": "グラフ",
    "nav.timeline": "タイムライン",
    "nav.trash": "ゴミ箱",
    "status.loading": "読み込み中…",
    "status.ready": "準備完了",
    "status.saved": "保存しました",
    "status.saving": "保存中…",
    "status.error": "問題が発生しました",
    "status.empty": "まだ何もありません",
    "status.offline": "オフラインで作業中",
    "a11y.panel.title": "アクセシビリティ",
    "a11y.panel.subtitle": "言語、コントラスト、フォーカス、ショートカットを確認します。",
    "a11y.audit.run": "アクセシビリティ監査を実行",
    "a11y.audit.score": "アクセシビリティスコア: {score}",
    "a11y.audit.issues": "{count} 件の問題が見つかりました",
    "a11y.audit.clean": "問題は見つかりませんでした",
    "a11y.contrast.title": "コントラストレポート",
    "a11y.contrast.ratio": "コントラスト比 {ratio} : 1",
    "a11y.contrast.pass": "{level} に適合",
    "a11y.contrast.fail": "{level} に不適合",
    "a11y.focus.title": "フォーカス順序",
    "a11y.focus.step": "手順 {order}: {label}",
    "a11y.focus.skip_link": "スキップリンクがあります",
    "a11y.shortcuts.title": "キーボードショートカット",
    "a11y.shortcuts.conflict": "{first} は {second} と競合します",
    "a11y.theme.title": "テーマ",
    "a11y.theme.picker": "テーマを選択",
    "a11y.locale.title": "言語",
    "a11y.locale.picker": "言語を選択",
    "a11y.direction": "文字方向",
    "a11y.reduce_motion": "動きを減らす",
    "a11y.high_contrast": "高コントラスト",
    "a11y.screen_reader_hints": "スクリーンリーダーのヒント",
    "a11y.announce.saved": "ノートを保存しました",
    "a11y.announce.deleted": "ノートをゴミ箱に移動しました",
    "a11y.announce.loaded": "{count} 件のノートを読み込みました",
    "plural.note.one": "{count} 件のノート",
    "plural.note.other": "{count} 件のノート",
    "plural.issue.one": "{count} 件の問題",
    "plural.issue.other": "{count} 件の問題",
    "format.date": "日付: {date}",
    "format.number": "数値: {value}",
}

ZH_MESSAGES: dict[str, str] = {
    "app.name": "RedScribe",
    "action.save": "保存",
    "action.cancel": "取消",
    "action.delete": "删除",
    "action.edit": "编辑",
    "action.open": "打开",
    "action.close": "关闭",
    "action.create": "创建",
    "action.retry": "重试",
    "action.apply": "应用",
    "action.reset": "重置",
    "action.search": "搜索",
    "nav.home": "首页",
    "nav.notes": "笔记",
    "nav.dashboard": "仪表盘",
    "nav.settings": "设置",
    "nav.help": "帮助",
    "nav.graph": "关系图",
    "nav.timeline": "时间线",
    "nav.trash": "回收站",
    "status.loading": "加载中…",
    "status.ready": "就绪",
    "status.saved": "已保存",
    "status.saving": "保存中…",
    "status.error": "出现问题",
    "status.empty": "这里还没有内容",
    "status.offline": "离线工作中",
    "a11y.panel.title": "无障碍",
    "a11y.panel.subtitle": "检查语言、对比度、焦点和快捷键。",
    "a11y.audit.run": "运行无障碍检查",
    "a11y.audit.score": "无障碍分数：{score}",
    "a11y.audit.issues": "发现 {count} 个问题",
    "a11y.audit.clean": "未发现问题",
    "a11y.contrast.title": "对比度报告",
    "a11y.contrast.ratio": "对比度 {ratio} 比 1",
    "a11y.contrast.pass": "符合 {level}",
    "a11y.contrast.fail": "低于 {level}",
    "a11y.focus.title": "焦点顺序",
    "a11y.focus.step": "第 {order} 步：{label}",
    "a11y.focus.skip_link": "跳转链接可用",
    "a11y.shortcuts.title": "键盘快捷键",
    "a11y.shortcuts.conflict": "{first} 与 {second} 冲突",
    "a11y.theme.title": "主题",
    "a11y.theme.picker": "选择主题",
    "a11y.locale.title": "语言",
    "a11y.locale.picker": "选择语言",
    "a11y.direction": "文字方向",
    "a11y.reduce_motion": "减少动态效果",
    "a11y.high_contrast": "高对比度",
    "a11y.screen_reader_hints": "屏幕阅读器提示",
    "a11y.announce.saved": "笔记已保存",
    "a11y.announce.deleted": "笔记已移至回收站",
    "a11y.announce.loaded": "已加载 {count} 条笔记",
    "plural.note.one": "{count} 条笔记",
    "plural.note.other": "{count} 条笔记",
    "plural.issue.one": "{count} 个问题",
    "plural.issue.other": "{count} 个问题",
    "format.date": "日期：{date}",
    "format.number": "数字：{value}",
}

BUILTIN_CATALOGS: dict[str, dict[str, str]] = {
    "en": EN_MESSAGES,
    "es": ES_MESSAGES,
    "fr": FR_MESSAGES,
    "de": DE_MESSAGES,
    "ar": AR_MESSAGES,
    "he": HE_MESSAGES,
    "ja": JA_MESSAGES,
    "zh": ZH_MESSAGES,
}


def placeholders_of(template: str) -> tuple[str, ...]:
    """Return placeholder names used in a message template."""
    return tuple(dict.fromkeys(PLACEHOLDER_RE.findall(template)))


@dataclass(frozen=True, slots=True)
class MessageCatalog:
    """A locale-specific set of message templates."""

    locale: str
    messages: dict[str, str] = field(default_factory=dict)
    description: str = ""

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self.messages))

    def has(self, key: str) -> bool:
        return key in self.messages

    def raw(self, key: str) -> str | None:
        return self.messages.get(key)

    def get(
        self,
        key: str,
        **params: Any,
    ) -> str:
        """Return an interpolated message, or the key when unavailable."""
        template = self.messages.get(key)
        if template is None:
            return key
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return template

    def missing_placeholders(self, key: str, **params: Any) -> tuple[str, ...]:
        """Return template placeholders that were not supplied."""
        template = self.messages.get(key)
        if template is None:
            return ()
        return tuple(name for name in placeholders_of(template) if name not in params)

    def entries(self) -> tuple[MessageEntry, ...]:
        return tuple(
            MessageEntry(key=key, text=text, placeholders=placeholders_of(text))
            for key, text in sorted(self.messages.items())
        )

    def merge(self, other: MessageCatalog) -> MessageCatalog:
        return MessageCatalog(
            locale=self.locale,
            messages={**self.messages, **other.messages},
            description=self.description or other.description,
        )

    def subset(self, prefixes: Sequence[str]) -> MessageCatalog:
        return MessageCatalog(
            locale=self.locale,
            messages={
                key: value
                for key, value in self.messages.items()
                if any(key.startswith(prefix) for prefix in prefixes)
            },
            description=self.description,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "description": self.description,
            "count": len(self.messages),
            "keys": list(self.keys),
            "messages": dict(self.messages),
        }


class CatalogManager:
    """Registry and resolver for message catalogs."""

    def __init__(self, catalogs: Mapping[str, MessageCatalog] | None = None) -> None:
        self._catalogs: dict[str, MessageCatalog] = {}
        for locale, builtin in BUILTIN_CATALOGS.items():
            self._catalogs[locale] = MessageCatalog(locale=locale, messages=dict(builtin))
        for locale, catalog in (catalogs or {}).items():
            self.register(
                catalog
                if catalog.locale == locale
                else MessageCatalog(locale, dict(catalog.messages))
            )

    def __contains__(self, locale: str) -> bool:
        return normalize_locale(locale) in self._catalogs

    @property
    def locales(self) -> tuple[str, ...]:
        return tuple(sorted(self._catalogs))

    def register(self, catalog: MessageCatalog) -> MessageCatalog:
        """Register a catalog, merging it with an existing locale catalog."""
        locale = normalize_locale(catalog.locale)
        current = self._catalogs.get(locale)
        self._catalogs[locale] = current.merge(catalog) if current else catalog
        return self._catalogs[locale]

    def catalog(self, locale: str) -> MessageCatalog | None:
        return self._catalogs.get(normalize_locale(locale))

    def translate(
        self,
        locale: str,
        key: str,
        **params: Any,
    ) -> str:
        """Translate a key using the locale fallback chain."""
        for candidate in fallback_chain(locale):
            catalog = self._catalogs.get(candidate)
            if catalog is not None and catalog.has(key):
                return catalog.get(key, **params)
        base = self.catalog(key.split(".", 1)[0])
        if base is not None and base.has(key):
            return base.get(key, **params)
        return self._catalogs.get("en", MessageCatalog("en")).get(key, **params)

    def coverage(self, locale: str, *, baseline: str = "en") -> dict[str, Any]:
        """Report translation coverage for a locale."""
        reference = self.catalog(baseline)
        catalog = self.catalog(locale)
        if reference is None:
            return {"locale": locale, "baseline": baseline, "coverage": 0.0}
        keys = set(reference.keys)
        if catalog is None:
            translated: set[str] = set()
        else:
            translated = {key for key in keys if catalog.has(key)}
        return {
            "locale": locale,
            "baseline": baseline,
            "total": len(keys),
            "translated": len(translated),
            "missing": sorted(keys - translated),
            "coverage": round(len(translated) / len(keys) * 100.0, 1) if keys else 100.0,
        }

    def coverage_report(self) -> dict[str, Any]:
        """Return coverage for every registered catalog."""
        return {
            "baseline": "en",
            "locales": {locale: self.coverage(locale) for locale in self.locales},
        }

    def all_entries(self, locale: str) -> tuple[MessageEntry, ...]:
        catalog = self.catalog(locale)
        return catalog.entries() if catalog else ()

    def is_complete(self, locale: str, *, baseline: str = "en") -> bool:
        coverage = self.coverage(locale, baseline=baseline)
        return bool(coverage.get("coverage", 0.0) >= 100.0)

    def plural(
        self,
        locale: str,
        key: str,
        count: int,
        *,
        categories: Sequence[str] = ("one", "other"),
    ) -> str:
        """Translate a plural key using a plural category."""
        category = (
            categories[0]
            if count == 1 and categories
            else (categories[-1] if categories else "other")
        )
        candidate = f"{key}.{category}"
        for option in (candidate, key):
            value = self.translate(locale, option, count=count)
            if value != option:
                return value
        return str(count)

    def keys(self) -> tuple[str, ...]:
        return self._catalogs.get("en", MessageCatalog("en")).keys

    def as_dict(self) -> dict[str, Any]:
        catalogs: dict[str, dict[str, Any]] = {}
        for locale in self.locales:
            catalog = self.catalog(locale)
            if catalog is not None:
                catalogs[locale] = catalog.as_dict()
        return {"locales": list(self.locales), "catalogs": catalogs}


def builtin_catalog(locale: str) -> MessageCatalog:
    """Return a built-in catalog for a locale, defaulting to English."""
    messages = BUILTIN_CATALOGS.get(normalize_locale(locale), EN_MESSAGES)
    return MessageCatalog(locale=normalize_locale(locale), messages=dict(messages))
