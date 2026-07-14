export const ONBOARDING_RESTART_EVENT = "onboarding-restart"

export function restartOnboarding(tourId) {
  window.dispatchEvent(new CustomEvent(ONBOARDING_RESTART_EVENT, { detail: { tourId } }))
}

function openAddMenu() {
  const btn = document.querySelector(".clt-add-btn")
  const menu = document.querySelector(".clt-add-menu")
  if (btn && !menu) btn.click()
}

function openAgentPanel() {
  const fab = document.querySelector(".canvas-agent-fab")
  const panel = document.querySelector(".agent-panel")
  if (fab && !panel?.classList.contains("agent-panel--open")) {
    fab.click()
  }
}

export const WORKSPACE_STEPS = [
  {
    selector: ".ws-entry",
    content: "从这里开始创建项目——上传剧本、AI 生成故事，或直接空白画布",
  },
  {
    selector: ".ws-tab-strip",
    content: "三种创作入口：上传已有剧本、让 AI 帮你生成故事、或进入自由画布",
  },
  {
    selector: ".ws-dropzone",
    content: "支持拖拽上传、粘贴剧本文本，或导入 Word 文档快速开拍",
  },
  {
    selector: ".ws-foot-skip",
    content: "不想从剧本开始？可以跳过，直接创建空白画布",
  },
  {
    selector: ".ws-tool-chips",
    content: "快捷入口：团队文件、视频审阅、公开审阅页，协作流程从这里进入",
  },
  {
    selector: ".ws-project-grid",
    content: "你的所有项目都在这里，点击卡片即可进入画布继续创作",
  },
  {
    selector: ".ws-project-new",
    content: "随时可以从这里新建空白项目，开始新的创作",
  },
  {
    selector: ".ws-util-capsule",
    content: "查看 Credits 额度、切换亮色/暗色主题，以及打开账户菜单",
  },
  {
    selector: ".ws-avatar-btn",
    content: "头像菜单：切换个人/团队空间、管理成员与权限、查看通知与帮助",
  },
]

export const CANVAS_STEPS = [
  {
    selector: ".ctb-project",
    content: "顶部项目名称与保存状态，点击可重命名当前项目",
  },
  {
    selector: '[data-tour="ctb-agent"]',
    content: "顶栏 Agent 开关：随时打开或关闭 AI 助手面板",
  },
  {
    selector: '[data-tour="ctb-credit"]',
    content: "用量额度：查看当前项目的图像/视频生成配额",
  },
  {
    selector: '[data-tour="ctb-share"]',
    content: "分享协作：邀请他人查看或编辑，支持多人实时协作",
  },
  {
    selector: ".clt-add-btn",
    content: "点击「+」添加节点——图像生成、视频生成、文本备注或上传素材",
  },
  {
    selector: ".clt-add-menu",
    content: "选择节点类型：图像生成卡片、视频节点、文本备注，或直接上传图片",
    beforeShow: openAddMenu,
  },
  {
    selector: '[data-tour="clt-assets"]',
    content: "素材库：浏览和管理项目内的图片、视频等素材资源",
  },
  {
    selector: '[data-tour="clt-history"]',
    content: "生成历史：查看过往生成记录，快速复用或下载",
  },
  {
    selector: '[data-tour="clt-comment"]',
    content: "评论批注：在画布上添加评论，与协作者讨论修改意见",
  },
  {
    selector: '[data-tour="clt-fullscreen"]',
    content: "全屏模式：隐藏浏览器边框，专注创作画布",
  },
  {
    selector: ".cbt-bar",
    content: "底栏：缩放画布、居中视图、开关小地图、吸附网格对齐节点",
  },
  {
    selector: ".canvas-agent-fab",
    content: "右下角 Agent 入口：描述你的想法，AI 自动生成分镜与节点",
  },
  {
    selector: ".agent-panel",
    content: "Agent 面板：在这里对话，生成的节点会直接出现在画布上",
    beforeShow: openAgentPanel,
  },
]
