import React, { useRef } from 'react';
import { Button, Nav, Tooltip } from '@douyinfe/semi-ui';
import {
  IconHome,
  IconUser,
  IconPlay,
  IconShoppingBag,
  IconOrderedList,
  IconFile,
  IconSetting,
  IconSun,
  IconMoon,
} from '@douyinfe/semi-icons';
import { useAppStore } from '../store/useAppStore';
import { gsap, useGSAP } from '../utils/animations';

interface SideNavProps {
  forceExpanded?: boolean;
  onNavigate?: () => void;
}

export const SideNav: React.FC<SideNavProps> = ({ forceExpanded = false, onNavigate }) => {
  const activeTab = useAppStore((s) => s.activeTab);
  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const isSidebarCollapsed = useAppStore((s) => s.isSidebarCollapsed);
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed);
  const isDarkMode = useAppStore((s) => s.isDarkMode);
  const setDarkMode = useAppStore((s) => s.setDarkMode);
  const collapsed = forceExpanded ? false : isSidebarCollapsed;
  const navRef = useRef<HTMLDivElement>(null);

  // 菜单项微动效：选中的菜单项图标轻弹激活 (遵循 gsap-react 规范)
  useGSAP(
    () => {
      if (!navRef.current) return;
      const selectedItem = navRef.current.querySelector('.semi-navigation-item-selected');
      if (selectedItem) {
        const icon = selectedItem.querySelector('.semi-navigation-item-icon');
        if (icon) {
          gsap.fromTo(
            icon,
            { scale: 0.82 },
            {
              scale: 1,
              duration: 0.28,
              ease: 'back.out(2)',
              overwrite: 'auto',
              clearProps: 'transform',
            }
          );
        }
      }
    },
    { scope: navRef, dependencies: [activeTab] }
  );

  const navItems = [
    { itemKey: 'dashboard', text: '数据看板', icon: <IconHome size="large" /> },
    { itemKey: 'accounts', text: '账号管理', icon: <IconUser size="large" /> },
    { itemKey: 'automation', text: '自动任务', icon: <IconPlay size="large" /> },
    { itemKey: 'store', text: '活动抢单', icon: <IconShoppingBag size="large" /> },
    { itemKey: 'orders', text: '小蚕订单', icon: <IconOrderedList size="large" /> },
    { itemKey: 'logs', text: '运行日志', icon: <IconFile size="large" /> },
    { itemKey: 'settings', text: '系统配置', icon: <IconSetting size="large" /> },
  ];

  return (
    <div ref={navRef} className="h-full flex flex-col">
      <Nav
        mode="vertical"
        isCollapsed={collapsed}
        onCollapseChange={(nextCollapsed) => {
          if (!forceExpanded) setSidebarCollapsed(nextCollapsed);
        }}
        selectedKeys={[activeTab]}
        onSelect={(data) => {
          const nextKey = String(data.itemKey);
          if (nextKey) {
            setActiveTab(nextKey);
            onNavigate?.();
          }
        }}
        style={{ flex: 1, minHeight: 0, height: 'auto', borderRight: 'none' }}
        header={{
          logo: collapsed ? (
            <Tooltip content="XiaoCan Assistant" position="right">
              <div
                className="w-10 h-10 flex items-center justify-center cursor-pointer transition-all duration-200 hover:scale-105 mx-auto"
                onClick={() => setActiveTab('dashboard')}
              >
                <img
                  src="/logo.png"
                  alt="XiaoCan Assistant"
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
                alt="XiaoCan Assistant"
                className="w-8 h-8 object-contain rounded-xl shadow-xs"
              />
            </div>
          ),
          text: (
            <div className="flex items-center gap-2 ml-2 cursor-pointer select-none" onClick={() => setActiveTab('dashboard')}>
              <span className="font-bold text-[16px] text-semi-color-text-0 tracking-tight hover:text-semi-color-primary transition-colors">
                XiaoCan Assistant
              </span>
            </div>
          ),
        }}
        items={navItems}
      />
      <div className={`side-theme-toggle shrink-0 flex items-center ${collapsed ? 'justify-center px-1' : 'justify-end px-3'} py-2`}>
        <Tooltip content={isDarkMode ? '切换为亮色主题' : '切换为暗黑主题'} position={collapsed ? 'right' : 'top'}>
          <Button
            theme="borderless"
            icon={isDarkMode ? <IconSun size="large" /> : <IconMoon size="large" />}
            onClick={() => setDarkMode(!isDarkMode)}
            className="text-semi-color-text-2 hover:bg-semi-color-fill-0 transition-colors"
            aria-label={isDarkMode ? '切换为亮色主题' : '切换为暗黑主题'}
          />
        </Tooltip>
      </div>
    </div>
  );
};
