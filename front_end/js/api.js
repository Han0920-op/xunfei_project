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
        headers: {
            'Content-Type': 'application/json'
        }
    };
    // POST请求的话，把数据放到请求体里
    if (data && method === 'POST') {
        config.body = JSON.stringify(data);
    }

    try {
        // 发送请求到后端
        const response = await fetch(BASE_URL + url, config);
        // 请求失败就抛出错误
        if (!response.ok) throw new Error('请求失败');
        // 把后端返回的JSON数据解析出来
        return await response.json();
    } catch (error) {
        // 出错了在控制台打印，同时弹提示
        console.error('接口请求错误：', error);
        alert('网络请求失败，请检查后端是否启动');
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
async function uploadImage(file) {
    // 图片上传要用FormData格式，不能用普通JSON
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(BASE_URL + '/vision/upload', {
        method: 'POST',
        body: formData
    });
    if (!response.ok) throw new Error('图片上传失败');
    return await response.json();
}
/**
 * 接口2：给Agent智能体发消息，获取回复
 * 对应后端：/agent/chat
 * 作用：把用户说的话、视觉结果发给Agent，返回Agent的回答/诊断结果
 * @param {object} data 对话数据，包含消息、视觉结果、案例ID
 */
async function sendChat(data) {
    return request('/agent/chat', 'POST', data);
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