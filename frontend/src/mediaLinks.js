export function extractMediaLinks(input) {
  const matches = input.match(/https?:\/\/[^\s<>"'`\[\]()，。！？；：、（）《》“”‘’「」『』【】]+/gi) || []
  return [...new Set(matches.map(link => link.replace(/\\/g, '').replace(/[.,!?;:}\]]+$/, '')))]
}
