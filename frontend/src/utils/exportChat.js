/**
 * Chat Export Utilities
 *
 * Supports exporting chat sessions to:
 * - Markdown (.md) - Simple, readable format
 * - Word (.docx) - Professional, formatted document
 */

import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  AlignmentType,
  BorderStyle,
  Table,
  TableRow,
  TableCell,
} from 'docx';

/**
 * Export chat session as Markdown
 * @param {Object} exportData - { session: {...}, messages: [...] }
 */
export async function exportAsMarkdown(exportData) {
  if (!exportData?.session || !exportData?.messages) {
    throw new Error('Invalid export data');
  }

  const { session, messages } = exportData;
  const stripCitations = (text = '') =>
    text.replace(/\[D\d+:p\d+\]/g, '').replace(/\s{2,}/g, ' ').trim();

  // Build markdown content
  let markdown = `# ${session.title}\n\n`;
  markdown += `**Date:** ${new Date(session.created_at).toLocaleString()}\n`;
  markdown += `**Documents:** ${session.document_count || 0} document(s)\n`;
  markdown += `**Messages:** ${messages.length} message(s)\n\n`;
  markdown += `---\n\n`;

  messages.forEach((msg, index) => {
    const role = msg.role === 'user' ? 'You' : 'Assistant';
    const timestamp = new Date(msg.created_at).toLocaleTimeString();

    markdown += `### ${role} · ${timestamp}\n\n`;
    markdown += `${stripCitations(msg.content)}\n\n`;

    if (index < messages.length - 1) {
      markdown += `---\n\n`;
    }
  });

  // Create and download file
  const blob = new Blob([markdown], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = sanitizeFilename(`${session.title}.md`);
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Export chat session as Word document with professional formatting
 * @param {Object} exportData - { session: {...}, messages: [...] }
 */
export async function exportAsWord(exportData) {
  if (!exportData?.session || !exportData?.messages) {
    throw new Error('Invalid export data');
  }

  const { session, messages } = exportData;

  const stripCitations = (text = '') =>
    text.replace(/\[D\d+:p\d+\]/g, '').replace(/\s{2,}/g, ' ').trim();

  const buildRunsFromText = (text = '', { size = 24, bold = false } = {}) => {
    const runs = [];
    const sanitized = stripCitations(text);
    if (!sanitized) return runs;

    const pattern = /(\*\*[^*]+\*\*)|(\*[^*]+\*)/g;
    let lastIndex = 0;
    let match;

    while ((match = pattern.exec(sanitized)) !== null) {
      if (match.index > lastIndex) {
        runs.push(new TextRun({ text: sanitized.slice(lastIndex, match.index), size, bold }));
      }

      const token = match[0];
      if (token.startsWith('**')) {
        runs.push(new TextRun({ text: token.slice(2, -2), bold: true, size }));
      } else if (token.startsWith('*')) {
        runs.push(new TextRun({ text: token.slice(1, -1), italics: true, size }));
      }

      lastIndex = match.index + token.length;
    }

    if (lastIndex < sanitized.length) {
      runs.push(new TextRun({ text: sanitized.slice(lastIndex), size, bold }));
    }

    return runs.length ? runs : [new TextRun({ text: sanitized, size, bold })];
  };

  const normalizeTableRow = (line) => {
    const trimmed = line.trim();
    const clean = trimmed.replace(/^\|/, '').replace(/\|$/, '');
    return clean.split('|').map((cell) => cell.trim());
  };

  const parseMarkdownBlocks = (content = '') => {
    const blocks = [];
    const lines = content.split('\n');
    let i = 0;

    while (i < lines.length) {
      const raw = lines[i];
      const line = raw.trim();

      if (!line) {
        i += 1;
        continue;
      }

      if (/^#{1,6}\s/.test(line)) {
        const level = Math.min(line.match(/^#+/)[0].length, 6);
        blocks.push({
          type: 'heading',
          level,
          text: line.replace(/^#{1,6}\s*/, ''),
        });
        i += 1;
        continue;
      }

      const nextLine = lines[i + 1]?.trim();
      const isTable = line.includes('|') && /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(nextLine || '');
      if (isTable) {
        const headerCells = normalizeTableRow(line);
        const rows = [];
        i += 2; // skip header + separator
        while (i < lines.length && lines[i].includes('|')) {
          const rowLine = lines[i].trim();
          if (!rowLine) break;
          rows.push(normalizeTableRow(rowLine));
          i += 1;
        }
        blocks.push({ type: 'table', headers: headerCells, rows });
        continue;
      }

      const paragraphLines = [line];
      i += 1;
      while (i < lines.length && lines[i].trim() && !/^#{1,6}\s/.test(lines[i].trim())) {
        const candidate = lines[i].trim();
        const candidateNext = lines[i + 1]?.trim();
        const candidateIsTable = candidate.includes('|') && /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(candidateNext || '');
        if (candidateIsTable) {
          break;
        }
        paragraphLines.push(candidate);
        i += 1;
      }
      blocks.push({ type: 'paragraph', text: paragraphLines.join(' ') });
    }

    return blocks;
  };

  // Build Word document
  const doc = new Document({
    sections: [
      {
        properties: {},
        children: [
          // Title
          new Paragraph({
            text: session.title,
            heading: HeadingLevel.HEADING_1,
            spacing: { after: 200 },
          }),

          // Metadata
          new Paragraph({
            children: [
              new TextRun({
                text: 'Date: ',
                bold: true,
              }),
              new TextRun({
                text: new Date(session.created_at).toLocaleString(),
              }),
            ],
            spacing: { after: 100 },
          }),

          new Paragraph({
            children: [
              new TextRun({
                text: 'Documents: ',
                bold: true,
              }),
              new TextRun({
                text: `${session.document_count || 0} document(s)`,
              }),
            ],
            spacing: { after: 100 },
          }),

          new Paragraph({
            children: [
              new TextRun({
                text: 'Messages: ',
                bold: true,
              }),
              new TextRun({
                text: `${messages.length} message(s)`,
              }),
            ],
            spacing: { after: 300 },
          }),

          // Divider
          new Paragraph({
            border: {
              bottom: {
                color: 'CCCCCC',
                space: 1,
                style: BorderStyle.SINGLE,
                size: 6,
              },
            },
            spacing: { after: 300 },
          }),

          // Messages
          ...messages.flatMap((msg, index) => {
            const role = msg.role === 'user' ? 'You' : 'Assistant';
            const timestamp = new Date(msg.created_at).toLocaleTimeString();
            const isUser = msg.role === 'user';

            const paragraphs = [
              // Role and timestamp
              new Paragraph({
                children: [
                  new TextRun({
                    text: `${role}`,
                    bold: true,
                    size: 24,
                    color: isUser ? '2563EB' : '059669', // primary blue or success green
                  }),
                  new TextRun({
                    text: ` · ${timestamp}`,
                    size: 20,
                    color: '6B7280', // muted
                  }),
                ],
                spacing: { before: 200, after: 150 },
              }),
            ];

            const blocks = parseMarkdownBlocks(msg.content || '');
            blocks.forEach((block) => {
              if (block.type === 'heading') {
                paragraphs.push(
                  new Paragraph({
                    children: buildRunsFromText(block.text, { size: 28, bold: true }),
                    heading:
                      block.level === 1
                        ? HeadingLevel.HEADING_1
                        : block.level === 2
                        ? HeadingLevel.HEADING_2
                        : HeadingLevel.HEADING_3,
                    spacing: { before: 200, after: 120 },
                  })
                );
                return;
              }

              if (block.type === 'table') {
                const tableRows = [
                  new TableRow({
                    children: block.headers.map(
                      (cell) =>
                        new TableCell({
                          margins: { top: 120, bottom: 120, left: 160, right: 160 },
                          children: [
                            new Paragraph({
                              children: buildRunsFromText(cell, { size: 24, bold: true }),
                              spacing: { after: 80 },
                            }),
                          ],
                        })
                    ),
                  }),
                  ...block.rows.map(
                    (row) =>
                      new TableRow({
                        children: row.map(
                          (cell) =>
                            new TableCell({
                              margins: { top: 120, bottom: 120, left: 160, right: 160 },
                              children: [
                                new Paragraph({
                                  children: buildRunsFromText(cell, { size: 24 }),
                                  spacing: { after: 80 },
                                }),
                              ],
                            })
                        ),
                      })
                  ),
                ];

                paragraphs.push(
                  new Table({
                    rows: tableRows,
                  })
                );
                paragraphs.push(
                  new Paragraph({
                    text: '',
                    spacing: { after: 200 },
                  })
                );
                return;
              }

              paragraphs.push(
                new Paragraph({
                  children: buildRunsFromText(block.text, { size: 24 }),
                  spacing: { after: 160 },
                  alignment: isUser ? AlignmentType.LEFT : AlignmentType.LEFT,
                })
              );
            });

            // Add divider between messages (except last)
            if (index < messages.length - 1) {
              paragraphs.push(
                new Paragraph({
                  border: {
                    bottom: {
                      color: 'E5E7EB',
                      space: 1,
                      style: BorderStyle.SINGLE,
                      size: 3,
                    },
                  },
                  spacing: { before: 150, after: 200 },
                })
              );
            }

            return paragraphs;
          }),
        ],
      },
    ],
  });

  // Generate and download
  const blob = await Packer.toBlob(doc);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = sanitizeFilename(`${session.title}.docx`);
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Sanitize filename for safe download
 * @param {string} filename - Original filename
 * @returns {string} - Sanitized filename
 */
function sanitizeFilename(filename) {
  return filename
    .replace(/[^a-z0-9.-]/gi, '-')
    .replace(/-+/g, '-')
    .toLowerCase();
}
