import React from 'react';
import { Nav, Tooltip, Tag } from '@douyinfe/semi-ui';
import {
  IconHome,
  IconUser,
  IconPlay,
  IconShoppingBag,
  IconOrderedList,
  IconFile,
  IconSetting,
} from '@douyinfe/semi-icons';
import { useAppStore } from '../store/useAppStore';

export const SideNav: React.FC = () => {
  const activeTab = useAppStore((s) => s.activeTab);
  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const isSidebarCollapsed = useAppStore((s) => s.isSidebarCollapsed);
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed);

  const navItems = [
    { itemKey: 'dashboard', text: '数据概览', icon: <IconHome size="large" /> },
    { itemKey: 'accounts', text: '账号管理', icon: <IconUser size="large" /> },
    { itemKey: 'automation', text: '自动任务', icon: <IconPlay size="large" /> },
    { itemKey: 'store', text: '商家抢单', icon: <IconShoppingBag size="large" /> },
    { itemKey: 'orders', text: '我的订单', icon: <IconOrderedList size="large" /> },
    { itemKey: 'logs', text: '运行日志', icon: <IconFile size="large" /> },
    { itemKey: 'settings', text: '系统配置', icon: <IconSetting size="large" /> },
  ];

  return (
    <div className="side-nav-root h-full flex flex-col">
      <Nav
        mode="vertical"
        isCollapsed={isSidebarCollapsed}
        onCollapseChange={(collapsed) => setSidebarCollapsed(collapsed)}
        selectedKeys={[activeTab]}
        onSelect={(data) => {
          const nextKey = String(data.itemKey);
          if (nextKey) {
            setActiveTab(nextKey);
          }
        }}
        style={{ height: '100%', borderRight: 'none' }}
        header={{
          logo: isSidebarCollapsed ? (
            <Tooltip content="小蚕助理" position="right">
              <div
                className="w-10 h-10 flex items-center justify-center cursor-pointer transition-all duration-200 hover:scale-105 mx-auto"
                onClick={() => setActiveTab('dashboard')}
              >
                <img
                  src="/logo.png"
                  alt="小蚕助理"
                  className="w-8.5 h-8.5 object-contain rounded-xl shadow-xs"
                />
              </div>
            </Tooltip>
          ) : (
            <div
              className="w-9 h-9 flex items-center justify-center cursor-pointer transition-transform duration-200 hover:scale-105 shrink-0"
              onClick={() => setActiveTab('dashboard')}
            >
              <img
                src="/logo.png"
                alt="小蚕助理"
                className="w-8 h-8 object-contain rounded-xl shadow-xs"
              />
            </div>
          ),
          text: (
            <div className="flex items-center gap-2 ml-2 cursor-pointer select-none" onClick={() => setActiveTab('dashboard')}>
              <span className="font-bold text-[16px] text-semi-color-text-0 tracking-tight hover:text-semi-color-primary transition-colors">
                小蚕助理
              </span>
              <Tag size="small" color="blue" type="light" shape="square" className="text-[10px] font-semibold px-1 py-0 scale-90 origin-left">
                助手版
              </Tag>
            </div>
          ),
        }}
        items={navItems}
      />
    </div>
  );
};
