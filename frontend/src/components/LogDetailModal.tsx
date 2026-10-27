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
import type { JobLog } from '../types';

const { Text } = Typography;

import { getTaskLabel } from '../constants/taskLabels';

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
  const accountNickname = matchedAccount?.nickname || accountKey || '默认账号';
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
                  [{l.created_at?.split(' ')[1] || l.created_at}] {getTaskLabel(l.task_id || '')} ({l.status === 'success' ? '成功' : l.status === 'failed' ? '失败' : l.status})
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
            border: '1px solid var(--semi-color-border)'
          }}
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
                    {matchedAccount?.nickname?.[0] || '用'}
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
                const lineIsStep = line.includes('步骤') || line.includes('场次') || line.includes('阶段');
                const lineIsSuccess = line.includes('成功') || line.includes('达成');
                const lineIsError = line.includes('失败') || line.includes('异常') || line.includes('未成功') || line.includes('代码:');
                const lineIsAborted = line.includes('中断') || line.includes('重启') || line.includes('终止');
                const lineIsRunning = line.includes('正在') || line.includes('检测') || line.includes('预热') || line.includes('持续') || line.includes('嗅探');

                let color = '#d4d4d4';
                if (lineIsStep) color = '#79b8ff';
                else if (lineIsSuccess) color = '#7ee787';
                else if (lineIsAborted) color = '#e3b341';
                else if (lineIsError) color = '#ff7b72';
                else if (lineIsRunning) color = '#f9d770';

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
