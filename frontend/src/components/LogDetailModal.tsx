import React, { useState, useEffect } from 'react';
import {
  Modal,
  Typography,
  Tag,
  Button,
  Space,
  Avatar,
  Toast,
  Descriptions,
  Select
} from '@douyinfe/semi-ui';
import {
  IconCopy,
  IconList,
  IconSpin
} from '@douyinfe/semi-icons';
import { useAppStore } from '../store/useAppStore';
import { getTaskLabel } from '../constants/taskLabels';
import { getLogAccountDisplay } from '../utils/logAccount';
import type { JobLog } from '../types';

const { Text } = Typography;


export interface LogDetailModalProps {
  visible: boolean;
  onClose: () => void;
  log?: JobLog | null;
  logs?: JobLog[];
  // 支持手动传入非 JobLog 对象的参数
  customTitle?: string;
  customTaskId?: string;
  customAccountKey?: string;
  customCreatedAt?: string;
  customStatus?: string;
  customOutput?: string;
}

export const LogDetailModal: React.FC<LogDetailModalProps> = ({
  visible,
  onClose,
  log,
  logs,
  customTitle,
  customTaskId,
  customAccountKey,
  customCreatedAt,
  customStatus,
  customOutput
}) => {
  const accounts = useAppStore((s) => s.accounts);
  const [selectedLog, setSelectedLog] = useState<JobLog | null>(log || null);

  useEffect(() => {
    setSelectedLog(log || null);
  }, [log]);

  const activeLog = selectedLog || log;
  const taskId = customTaskId || activeLog?.task_id || '';
  const taskName = customTitle || getTaskLabel(taskId);
  const accountKey = customAccountKey || activeLog?.account_key || '';
  const matchedAccount = accounts.find((a) => a.key === accountKey);
  const accountDisplay = getLogAccountDisplay({
    account_key: accountKey,
    account_name: activeLog?.account_name,
    account_type: activeLog?.account_type,
  }, matchedAccount);
  const accountNickname = accountDisplay.name;
  const createdAt = customCreatedAt || activeLog?.created_at || '-';
  const status = customStatus || activeLog?.status || 'success';
  const output = customOutput !== undefined ? customOutput : (activeLog?.output || '');

  const handleCopy = () => {
    if (!output) {
      Toast.warning('当前无日志可复制');
      return;
    }
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(output).then(
        () => Toast.success('已复制全部日志到剪贴板'),
        () => Toast.error('复制失败，请手动选中文本复制')
      );
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = output;
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        Toast.success('已复制全部日志到剪贴板');
      } catch {
        Toast.error('复制失败，请手动复制');
      }
      document.body.removeChild(textarea);
    }
  };

  const isRunning = status === 'running';
  const isSuccess = status === 'success';
  const isAborted = status === 'aborted';

  return (
    <Modal
      title={`日志详情 - [${taskName}]`}
      visible={visible}
      onCancel={onClose}
      footer={
        <div className="flex justify-between items-center w-full">
          <Button
            theme="light"
            type="tertiary"
            icon={<IconCopy />}
            onClick={handleCopy}
          >
            复制全部日志
          </Button>
          <Button theme="solid" type="primary" onClick={onClose}>
            关闭
          </Button>
        </div>
      }
      width={680}
      centered
    >
      <div className="space-y-3 pt-1">
        {/* 多条日志切换条 */}
        {logs && logs.length > 1 && (
          <div className="flex items-center justify-between bg-semi-color-fill-0 border border-semi-color-border rounded-lg p-2 px-3">
            <Text size="small" type="secondary">
              切换查看历史日志流水（共 {logs.length} 条）：
            </Text>
            <Select
              size="small"
              style={{ width: 280 }}
              value={activeLog?.id}
              onChange={(val) => {
                const found = logs.find((l) => l.id === val);
                if (found) setSelectedLog(found);
              }}
            >
              {logs.map((l) => (
                <Select.Option key={l.id} value={l.id}>
                  [{l.created_at?.split(' ')[1] || l.created_at}] {getTaskLabel(l.task_id)} ({l.status === 'success' ? '成功' : l.status === 'failed' ? '失败' : l.status})
                </Select.Option>
              ))}
            </Select>
          </div>
        )}

        {/* 元信息条：采用官方 Descriptions 组件结构化展示 */}
        <Descriptions
          size="small"
          row={false}
          style={{
            padding: '10px 16px',
            backgroundColor: 'var(--semi-color-fill-0)',
            borderRadius: 'var(--semi-border-radius-medium)',
            border: '1px solid var(--semi-color-border)',
            maxWidth: '100%',
            overflow: 'hidden'
          }}
          className="[&_.semi-description-item]:min-w-0 [&_.semi-description-item-content]:min-w-0 [&_.semi-description-item-content]:max-w-full"
          data={[
            {
              key: '执行时间',
              value: <Text code size="small">{createdAt}</Text>
            },
            {
              key: '执行账号',
              value: (
                <Space spacing="tight">
                  <Avatar
                    size="extra-extra-small"
                    src={matchedAccount?.avatar || undefined}
                    color="orange"
                  >
                    {matchedAccount?.nick_name?.[0] || ''}
                  </Avatar>
                  <Text strong ellipsis={{ showTooltip: true }} style={{ maxWidth: 140 }}>
                    {accountNickname}
                  </Text>
                </Space>
              )
            },
            {
              key: '状态',
              value: (
                <Tag
                  color={isRunning ? 'blue' : isSuccess ? 'green' : isAborted ? 'amber' : 'red'}
                  size="small"
                  prefixIcon={isRunning ? <IconSpin spin /> : undefined}
                >
                  {isRunning ? '正在执行中' : isSuccess ? '执行成功' : isAborted ? '已中断终止' : '执行异常'}
                </Tag>
              )
            },
            {
              key: '执行结果',
              value: (
                <div
                  className="min-w-0 max-w-full break-words whitespace-normal leading-relaxed"
                  style={{ maxWidth: 460 }}
                  title={String(activeLog?.result || '').trim() || '—'}
                >
                  <Text
                    size="small"
                    className={/401|403|429|WAF|STGW|STGM|风控|拦截|失败|失效|异常|错误码|被拒绝|冷却|跳过|低于门槛|余额不足|元宝不足|资格拦截|未中签|未命中|售罄|已领完|名额已发完|名额已用完|无资格|不满足|未开通|未绑定/.test(String(activeLog?.result || '')) ? 'text-red-500' : ''}
                  >
                    {String(activeLog?.result || '').trim() || '—'}
                  </Text>
                </div>
              )
            }
          ]}
        />

        {/* 步骤流水结构化可视化解析 */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs text-semi-color-text-1 font-medium">
            <IconList size="small" />
            <span>详细执行步骤过程：</span>
          </div>
          <div className="bg-[#1e1e1e] text-[#d4d4d4] p-4 rounded-xl font-mono text-[12px] max-h-[380px] overflow-y-auto whitespace-pre-wrap leading-relaxed shadow-inner select-text">
            {output ? (
              output.split('\n').map((line, idx) => {
                const lineIsStep = line.includes('步骤') || line.includes('场次') || line.includes('阶段') || line.includes('开始执行') || line.includes('处理完毕');

                // 状态通告、已完成/重复完成、进行中、核验等呈现黄色通知高亮
                const lineIsNotice = 
                  line.includes('已完成') ||
                  line.includes('重复完成') ||
                  line.includes('无需重复') ||
                  line.includes('已打卡') ||
                  line.includes('已生效') ||
                  line.includes('已触发') ||
                  line.includes('未完成') ||
                  line.includes('正在') ||
                  line.includes('检测') ||
                  line.includes('预热') ||
                  line.includes('持续') ||
                  line.includes('嗅探') ||
                  line.includes('提示') ||
                  line.includes('拦截') ||
                  line.includes('待命') ||
                  line.includes('资产状态同步');

                // 新鲜达成或斩获元宝入账呈现绿色高亮
                const lineIsSuccess = 
                  (line.includes('成功') || line.includes('达成') || line.includes('已入账') || line.includes('斩获') || line.includes('抢兑成功')) &&
                  !line.includes('未成功') &&
                  !line.includes('失败') &&
                  !line.includes('已完成');

                const lineIsAborted = line.includes('中断') || line.includes('重启') || line.includes('终止');

                // 排除正常完成状态后的真正接口报错标红
                const lineIsError = 
                  line.includes('失败') ||
                  line.includes('异常') ||
                  line.includes('未成功') ||
                  line.includes('错误') ||
                  line.includes('403') ||
                  line.includes('401') ||
                  line.includes('500') ||
                  (line.includes('代码:') && !line.includes('已完成') && !line.includes('重复完成'));

                let color = '#d4d4d4';
                if (lineIsStep) color = '#79b8ff';
                else if (lineIsNotice) color = '#f9d770';
                else if (lineIsSuccess) color = '#7ee787';
                else if (lineIsAborted) color = '#e3b341';
                else if (lineIsError) color = '#ff7b72';

                return (
                  <div key={idx} style={{ color }} className="py-0.5">
                    {line}
                  </div>
                );
              })
            ) : (
              <span className="text-gray-500">无日志内容</span>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
