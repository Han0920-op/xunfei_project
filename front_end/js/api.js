// ==================== 全局配置 ====================
// 后端接口的基础地址
const BASE_URL = 'http://127.0.0.1:8000';


// ==================== 通用请求函数 ====================
/**
 * 通用的网络请求封装，所有接口都调用这个函数
 * @param {string} url    接口路径，比如 '/vision/upload'
 * @param {string} method 请求方式，GET 或 POST
 * @param {object} data   要传给后端的数据
 */
async function request(url, method = 'GET', data = null) {
    // 配置请求信息
    const config = {
        method: method,
        headers: {}
    };
    // POST / PUT 等有请求体时才设置 Content-Type 和 body
    if (data !== null && data !== undefined) {
        config.headers['Content-Type'] = 'application/json';
        config.body = JSON.stringify(data);
    }

    try {
        // 发送请求到后端
        const response = await fetch(BASE_URL + url, config);
        // 请求成功就解析 JSON 返回
        if (response.ok) {
            return await response.json();
        }
        // 请求失败：尝试读取后端返回的错误详情
        let detail = `${response.status} ${response.statusText}`;
        try {
            const body = await response.json();
            if (body.detail) detail = body.detail;
        } catch (_) {
            // 响应体不是 JSON，使用默认的 status+statusText
        }
        throw new Error(detail);
    } catch (error) {
        // 网络层面的错误（断网、CORS、后端未启动等）原样抛出，
        // 不再弹通用 alert，由各调用方根据场景展示合适的提示。
        console.error('接口请求错误：', error);
        throw error;
    }
}


// ==================== 具体接口函数 ====================
/**
 * 接口1：上传图片，获取视觉模型分析结果
 * 对应后端：/vision/upload
 * 作用：把用户上传的小麦图片发给后端，返回叶片颜色、异常程度等结构化数据
 * @param {File} file 选中的图片文件对象
 */
async function uploadImage(file, question, caseId) {
    // 图片上传要用FormData格式，不能用普通JSON
    const formData = new FormData();
    formData.append('file', file);
    formData.append('question', question || '请详细描述这张小麦图片的生长状况，包括作物类型、叶片颜色、斑点、异常程度等可见特征');
    if (caseId) formData.append('case_id', caseId);   // 复查模式：给已有案例追加图片，不新建案例
    const response = await fetch(BASE_URL + '/vision/upload', {
        method: 'POST',
        body: formData
    });
    if (!response.ok) {
        const error = await response.text();
        throw new Error(`图片分析失败: ${error}`);
    }
    return await response.json();
}
/**
 * 接口2：给Agent智能体发消息，获取回复
 * 对应后端：/agent/chat
 * 作用：把用户说的话、视觉结果发给Agent，返回Agent的回答/诊断结果
 * @param {object} data 对话数据，包含消息、视觉结果、案例ID
 */
async function sendChat(data) {
    return request('/chat', 'POST', {
        message: data.message,
        conversation_id: data.conversation_id ?? null,
        vision_result: data.vision_result ?? null,
        case_id: data.case_id ?? null,
        image_path: data.image_path ?? null
    });
}
/**
 * 接口2.5：按会话 ID 读回完整聊天记录
 * 对应后端：/conversation/{conversationId}/messages
 * 作用：页面刷新 / 从历史案例进入复查时，恢复历史对话
 */
async function getConversationMessages(conversationId) {
    return request(`/conversation/${conversationId}/messages`, 'GET');
}
/**
 * 接口3：获取历史案例列表
 * 对应后端：/history/list
 * 作用：获取所有曾经诊断过的案例，展示在历史页面
 */
async function getHistoryList() {
    return request('/history/list', 'GET');
}
/**
 * 接口4：获取单个案例的详细信息
 * 对应后端：/history/detail/案例ID
 * 作用：点击历史卡片时，获取这个案例的完整诊断信息
 * @param {string} caseId 案例的唯一ID
 */
async function getCaseDetail(caseId) {
    return request(`/history/detail/${caseId}`, 'GET');
}
/**
 * 接口4.5：获取某个案例的全部复查记录
 * 对应后端：/history/{caseId}/rechecks
 */
async function getRechecks(caseId) {
    return request(`/history/${caseId}/rechecks`, 'GET');
}
/**
 * 接口4.6：删除一个历史案例
 * 对应后端：DELETE /history/{caseId}
 */
async function deleteCase(caseId) {
    return request(`/history/${caseId}`, 'DELETE');
}
/**
 * 接口4.7：手动结束跟踪，把案例标记为「已完成」
 * 对应后端：POST /history/{caseId}/finish
 */
async function finishCase(caseId) {
    return request(`/history/${caseId}/finish`, 'POST');
}
/**
 * 接口5：复查对比接口
 * 对应后端：/history/compare
 * 作用：上传新图片，和历史案例做对比，看长势变化
 * @param {string} caseId 历史案例ID
 * @param {File} file   新上传的图片
 */
async function compareCase(caseId, file) {
    const formData = new FormData();
    formData.append('case_id', caseId);
    formData.append('file', file);
    const response = await fetch(BASE_URL + '/history/compare', {
        method: 'POST',
        body: formData
    });
    if (!response.ok) throw new Error('对比失败');
    return await response.json();
}