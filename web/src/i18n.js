// Chinese labels for official source tags (OpenAI 20 + Claude 5 + Apple 2;
// single source of truth for the translate toggle). Unknown tags (open-vocab
// sources like google-blog / nvidia-blog) fall back to the original English.
export const TAG_ZH = {
  'Company': '公司',
  'Research': '研究',
  'Product': '产品',
  'Global Affairs': '全球事务',
  'Story': '故事',
  'Safety & Alignment': '安全与对齐',
  'Safety': 'AI 安全',
  'OpenAI Academy': 'OpenAI 学院',
  'Publication': '论文发表',
  'Security': '信息安全',
  'Engineering': '工程',
  'API': 'API',
  'AI Adoption': 'AI 落地',
  'Release': '发布',
  'Startup': '初创',
  'ChatGPT': 'ChatGPT',
  'Guides': '指南',
  'Applied AI': '应用 AI',
  'Webinar': '网络研讨会',
  'OpenAI on OpenAI': 'OpenAI 谈 OpenAI',
  'Product announcements': '产品发布',
  'Enterprise AI': '企业 AI',
  'Claude Code': 'Claude Code',
  'Agents': '智能体',
  'eBook': '电子书',
  'PRESS RELEASE': '新闻稿',
  'UPDATE': '更新',
}

export function tagLabel(tag, showZh) {
  return showZh ? TAG_ZH[tag] || tag : tag
}
