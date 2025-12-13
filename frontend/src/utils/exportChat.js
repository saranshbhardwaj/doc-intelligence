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
    markdown += `${msg.content}\n\n`;

    if (msg.source_chunks && msg.source_chunks.length > 0) {
      markdown += `*📚 Sources: ${msg.num_chunks_retrieved} chunks retrieved*\n\n`;
    }

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

              // Message content
              new Paragraph({
                text: msg.content,
                spacing: { after: 100 },
                alignment: isUser ? AlignmentType.LEFT : AlignmentType.LEFT,
              }),
            ];

            // Add sources if available
            if (msg.source_chunks && msg.source_chunks.length > 0) {
              paragraphs.push(
                new Paragraph({
                  children: [
                    new TextRun({
                      text: `📚 Sources: ${msg.num_chunks_retrieved} chunks retrieved`,
                      italics: true,
                      size: 18,
                      color: '6B7280',
                    }),
                  ],
                  spacing: { after: 100 },
                })
              );
            }

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
