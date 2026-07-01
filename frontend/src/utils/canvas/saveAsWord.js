/** 将纯文本导出为 .doc（HTML 包装，Word 可打开） */
export function saveAsWord(content, filename = "export") {
  const htmlContent = (content || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br/>")

  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:w="urn:schemas-microsoft-com:office:word"
xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><title>${filename}</title></head>
<body><p>${htmlContent}</p></body></html>`

  const blob = new Blob([html], { type: "application/msword" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${filename}.doc`
  a.click()
  URL.revokeObjectURL(url)
}
