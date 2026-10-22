"use client";

import React, { useState, useMemo, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  useRun,
  useCatalog,
  useAppMap,
  useReviewLog,
  useSubmitReview,
  useUpdateCatalogTest,
} from "@/lib/api/hooks";
import { useRunStream } from "@/hooks/useRunStream";
import { useUiStore } from "@/lib/store/uiStore";
import { useToast } from "@/components/ui/Toast";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Drawer } from "@/components/ui/Drawer";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { Checkbox } from "@/components/ui/Checkbox";
import { Stepper } from "@/components/ui/Stepper";
import {
  type CatalogTest,
  type AppMapNode,
  type TestPriority,
  type TestReviewStatus,
} from "@/types";
import { extractHostname, formatRelativeTime } from "@/lib/utils";
import {
  Search,
  Check,
  X,
  Edit2,
  ListChecks,
  Network,
  History,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  Play,
  Bot,
  User,
  Sparkles,
  ArrowRight,
} from "lucide-react";

export default function CatalogRunPage() {
  const params = useParams();
  const runId = params.runId as string;
  const router = useRouter();
  const { toast } = useToast();
  const { setSelectedRunId } = useUiStore();

  useEffect(() => {
    if (runId) setSelectedRunId(runId);
  }, [runId, setSelectedRunId]);

  const { data: run, isLoading: isRunLoading } = useRun(runId);
  const { data: catalog, isLoading: isCatalogLoading } = useCatalog(runId);
  const { data: appMap, isLoading: isAppMapLoading } = useAppMap(runId);
  const { data: reviewLog, isLoading: isReviewLogLoading } = useReviewLog(runId);

  // SSE subscription to receive catalog updates in real-time
  const isTerminal =
    run?.status === "completed" ||
    run?.status === "failed" ||
    run?.status === "cancelled";
  useRunStream(runId, isTerminal);

  // Mutations
  const { mutate: submitReview, isPending: isReviewPending } =
    useSubmitReview(runId);
  const { mutate: updateTest, isPending: isUpdatePending } =
    useUpdateCatalogTest(runId);

  // State
  const [searchQuery, setSearchQuery] = useState("");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedTestIds, setSelectedTestIds] = useState<string[]>([]);
  const [editingTest, setEditingTest] = useState<CatalogTest | null>(null);

  // Reject Modal state
  const [rejectingTest, setRejectingTest] = useState<CatalogTest | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Review Log Drawer
  const [isLogDrawerOpen, setIsLogDrawerOpen] = useState(false);

  // Edit form state
  const [editTitle, setEditTitle] = useState("");
  const [editExpected, setEditExpected] = useState("");
  const [editStepsText, setEditStepsText] = useState("");
  const [editPriority, setEditPriority] = useState<TestPriority>("medium");

  const openEditDrawer = (test: CatalogTest) => {
    setEditingTest(test);
    setEditTitle(test.title);
    setEditExpected(test.expected_result);
    setEditStepsText((test.steps || []).join("\n"));
    setEditPriority(test.priority);
  };

  const handleSaveEdit = () => {
    if (!editingTest) return;
    const stepsArray = editStepsText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

    updateTest(
      {
        testId: editingTest.id,
        updates: {
          title: editTitle,
          expected_result: editExpected,
          steps: stepsArray,
          priority: editPriority,
        },
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "Test updated",
            message: `Updated ${editTitle}`,
          });
          setEditingTest(null);
        },
        onError: (err) => {
          toast({
            type: "error",
            title: "Failed to update test",
            message: err.message,
          });
        },
      }
    );
  };

  const handleApproveSingle = (test: CatalogTest) => {
    submitReview(
      {
        test_ids: [test.id],
        decision: "approved",
        reason: "Approved manually",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "Test approved",
            message: `Approved "${test.title}"`,
          });
        },
      }
    );
  };

  const handleConfirmReject = () => {
    if (!rejectingTest) return;
    if (!rejectReason.trim()) {
      toast({
        type: "error",
        title: "Reason required",
        message: "Please state why this test is being rejected.",
      });
      return;
    }

    submitReview(
      {
        test_ids: [rejectingTest.id],
        decision: "rejected",
        reason: rejectReason.trim(),
      },
      {
        onSuccess: () => {
          toast({
            type: "info",
            title: "Test rejected",
            message: `Rejected "${rejectingTest.title}"`,
          });
          setRejectingTest(null);
          setRejectReason("");
        },
      }
    );
  };

  const handleBulkApprove = () => {
    if (selectedTestIds.length === 0) return;
    submitReview(
      {
        test_ids: selectedTestIds,
        decision: "approved",
        reason: "Bulk approved from catalog",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "Tests approved",
            message: `${selectedTestIds.length} tests approved`,
          });
          setSelectedTestIds([]);
        },
      }
    );
  };

  const handleApproveAllAndRun = () => {
    const allPending = (catalog || [])
      .filter((t) => t.review_status === "pending")
      .map((t) => t.id);

    if (allPending.length === 0) {
      toast({
        type: "info",
        title: "No pending tests",
        message: "All tests have already been reviewed.",
      });
      return;
    }

    submitReview(
      {
        test_ids: allPending,
        decision: "approved",
        reason: "All pending tests approved. Advancing to execution.",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "All tests approved",
            message: "Execution beginning now.",
          });
          router.push(`/execution/${runId}`);
        },
      }
    );
  };

  // Filtered catalog tests
  const filteredCatalog = useMemo(() => {
    if (!catalog) return [];
    return catalog.filter((test) => {
      const matchesSearch =
        test.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        test.expected_result.toLowerCase().includes(searchQuery.toLowerCase()) ||
        test.spec_item_ids.some((id) =>
          id.toLowerCase().includes(searchQuery.toLowerCase())
        );

      const matchesPriority =
        priorityFilter === "all" || test.priority === priorityFilter;
      const matchesStatus =
        statusFilter === "all" || test.review_status === statusFilter;

      return matchesSearch && matchesPriority && matchesStatus;
    });
  }, [catalog, searchQuery, priorityFilter, statusFilter]);

  const isExploringOrPlanning =
    run?.status === "exploring" || run?.status === "planning";

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-24">
      {/* Run Header */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-heading text-xl font-normal text-[#141413]">
              {run ? extractHostname(run.target_url) : "Loading..."}
            </span>
            <Chip variant={run?.status || "neutral"} size="sm">
              {run?.status || "loading"}
            </Chip>
            <span className="text-xs font-mono text-[#8A887F]">
              Mode: {run?.review_mode || "manual"}
            </span>
          </div>
          {run?.prompt && (
            <p className="text-xs text-[#6B6A64] mt-1 max-w-2xl">
              {run.prompt}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsLogDrawerOpen(true)}
            className="gap-1.5"
          >
            <History className="w-3.5 h-3.5" />
            <span>Review Log ({reviewLog?.length ?? 0})</span>
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => router.push(`/execution/${runId}`)}
            className="gap-1.5"
          >
            <Play className="w-3.5 h-3.5 text-[#D97757]" />
            <span>Execution View</span>
          </Button>
        </div>
      </div>

      {/* When run is still exploring or planning, show live progress card instead of empty catalog */}
      {isExploringOrPlanning ? (
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-8 shadow-xs text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-[#F6EDE8] text-[#D97757] flex items-center justify-center mx-auto animate-pulse">
            <Sparkles className="w-6 h-6 stroke-[1.75]" />
          </div>
          <div>
            <h3 className="font-heading text-xl font-normal text-[#141413]">
              {run?.status === "exploring"
                ? "Explorer Agent Mapping Application..."
                : "Planner Agent Building Test Catalog..."}
            </h3>
            <p className="text-xs text-[#6B6A64] max-w-md mx-auto mt-1 leading-relaxed">
              The agent pipeline is actively discovering interactive flows,
              endpoints, and linking test scenarios to your specification. Tests
              will populate here automatically as they are planned.
            </p>
          </div>
          <div className="max-w-md mx-auto pt-2">
            <Stepper status={run?.status || "exploring"} />
          </div>
        </div>
      ) : (
        <Tabs defaultValue="catalog" className="w-full">
          <TabsList className="mb-4">
            <TabsTrigger value="catalog" className="gap-1.5">
              <ListChecks className="w-4 h-4" />
              <span>Test Catalog ({catalog?.length ?? 0})</span>
            </TabsTrigger>
            <TabsTrigger value="appmap" className="gap-1.5">
              <Network className="w-4 h-4" />
              <span>Discovered App Map</span>
            </TabsTrigger>
          </TabsList>

          {/* TAB 1: TEST CATALOG */}
          <TabsContent value="catalog" className="space-y-4">
            {/* Filters Bar */}
            <div className="bg-white border border-[#E3DACC] rounded-xl p-3 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-xs">
              {/* Search */}
              <div className="relative flex-1 max-w-sm">
                <Search className="w-4 h-4 text-[#8A887F] absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search catalog by title, spec ID, expected..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] focus:outline-none focus:ring-1 focus:ring-[#D97757]"
                />
              </div>

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {/* Priority filter */}
                <select
                  value={priorityFilter}
                  onChange={(e) => setPriorityFilter(e.target.value)}
                  className="px-2.5 py-1.5 bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] text-xs focus:outline-none"
                >
                  <option value="all">All Priorities</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>

                {/* Status filter */}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-2.5 py-1.5 bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] text-xs focus:outline-none"
                >
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
            </div>

            {/* Catalog Table */}
            {isCatalogLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : filteredCatalog.length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="No tests match filter"
                description="Try clearing search or filters to see all planned catalog tests."
              />
            ) : (
              <div className="bg-white border border-[#E3DACC] rounded-[16px] overflow-hidden shadow-xs">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-[#FAF9F5] border-b border-[#E3DACC] text-[#6B6A64]">
                      <th className="p-3 w-10">
                        <Checkbox
                          checked={
                            selectedTestIds.length > 0 &&
                            selectedTestIds.length === filteredCatalog.length
                          }
                          onCheckedChange={(checked) => {
                            if (checked) {
                              setSelectedTestIds(filteredCatalog.map((t) => t.id));
                            } else {
                              setSelectedTestIds([]);
                            }
                          }}
                        />
                      </th>
                      <th className="py-3 px-3 font-semibold">Test Details</th>
                      <th className="py-3 px-3 font-semibold">Spec Links</th>
                      <th className="py-3 px-3 font-semibold">Priority</th>
                      <th className="py-3 px-3 font-semibold">Review Status</th>
                      <th className="py-3 px-3 font-semibold text-right">
                        Actions
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-[#E3DACC]/60">
                    {filteredCatalog.map((test) => {
                      const isSelected = selectedTestIds.includes(test.id);

                      return (
                        <tr
                          key={test.id}
                          className={`hover:bg-[#FAF9F5]/70 transition-colors ${
                            isSelected ? "bg-[#FAF9F5]" : ""
                          }`}
                        >
                          <td className="p-3">
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={(checked) => {
                                if (checked) {
                                  setSelectedTestIds((prev) => [
                                    ...prev,
                                    test.id,
                                  ]);
                                } else {
                                  setSelectedTestIds((prev) =>
                                    prev.filter((id) => id !== test.id)
                                  );
                                }
                              }}
                            />
                          </td>

                          <td className="py-3.5 px-3 min-w-[240px]">
                            <p className="font-medium text-[#141413] text-sm">
                              {test.title}
                            </p>
                            <p className="text-xs text-[#6B6A64] mt-0.5 line-clamp-1">
                              Expected: {test.expected_result}
                            </p>
                            <div className="flex items-center gap-1 mt-1 text-[11px] text-[#8A887F] font-mono">
                              <span>{test.steps?.length ?? 0} steps</span>
                            </div>
                          </td>

                          <td className="py-3.5 px-3">
                            <div className="flex flex-wrap gap-1">
                              {test.spec_item_ids.length > 0 ? (
                                test.spec_item_ids.map((id) => (
                                  <span
                                    key={id}
                                    className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-[#F0EEE6] border border-[#E3DACC] text-[#6B6A64]"
                                  >
                                    {id}
                                  </span>
                                ))
                              ) : (
                                <span className="text-[#8A887F] text-xs">-</span>
                              )}
                            </div>
                          </td>

                          <td className="py-3.5 px-3">
                            <Chip variant={test.priority} size="xs">
                              {test.priority}
                            </Chip>
                          </td>

                          <td className="py-3.5 px-3">
                            <div>
                              <Chip variant={test.review_status} size="xs">
                                {test.review_status}
                              </Chip>
                              {test.last_decision && (
                                <p className="text-[10px] text-[#8A887F] mt-1 flex items-center gap-1">
                                  {test.last_decision.actor ===
                                  "reviewer_agent" ? (
                                    <Bot className="w-3 h-3 text-[#D97757]" />
                                  ) : (
                                    <User className="w-3 h-3" />
                                  )}
                                  <span className="truncate max-w-[120px]">
                                    {test.last_decision.reason || "Decided"}
                                  </span>
                                </p>
                              )}
                            </div>
                          </td>

                          <td className="py-3.5 px-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              {test.review_status !== "approved" && (
                                <button
                                  onClick={() => handleApproveSingle(test)}
                                  title="Approve test"
                                  className="p-1.5 rounded-lg text-[#5E8C61] hover:bg-[#EBF2EB] border border-[#D2E3D3] transition-colors cursor-pointer"
                                >
                                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                                </button>
                              )}

                              {test.review_status !== "rejected" && (
                                <button
                                  onClick={() => {
                                    setRejectingTest(test);
                                    setRejectReason("");
                                  }}
                                  title="Reject test"
                                  className="p-1.5 rounded-lg text-[#C4473A] hover:bg-[#FAEBE9] border border-[#F2CAC5] transition-colors cursor-pointer"
                                >
                                  <X className="w-3.5 h-3.5 stroke-[2.5]" />
                                </button>
                              )}

                              <button
                                onClick={() => openEditDrawer(test)}
                                title="Edit test"
                                className="p-1.5 rounded-lg text-[#6B6A64] hover:bg-[#F0EEE6] border border-[#E3DACC] transition-colors cursor-pointer"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>

          {/* TAB 2: APP MAP TREE */}
          <TabsContent value="appmap">
            <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60">
                <div>
                  <h3 className="font-heading text-lg font-normal text-[#141413]">
                    Discovered Application Architecture
                  </h3>
                  <p className="text-xs text-[#6B6A64]">
                    Pages, routes, and actionable elements discovered by the
                    Explorer agent
                  </p>
                </div>

                {appMap && (
                  <div className="text-xs font-mono px-3 py-1 bg-[#F0EEE6] border border-[#E3DACC] rounded-full text-[#141413]">
                    Budget: {appMap.total_pages} / {appMap.max_pages_budget}{" "}
                    pages crawled
                  </div>
                )}
              </div>

              {isAppMapLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-3/4 ml-6" />
                  <Skeleton className="h-10 w-1/2 ml-12" />
                </div>
              ) : !appMap?.root_node ? (
                <EmptyState
                  icon={Network}
                  title="No app map available"
                  description="Explorer agent has not yet mapped the application routes."
                />
              ) : (
                <AppMapTreeNode node={appMap.root_node} />
              )}
            </div>
          </TabsContent>
        </Tabs>
      )}

      {/* Sticky Action Bar */}
      <div className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-xs border-t border-[#E3DACC] py-3.5 px-8 shadow-lg">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="text-xs text-[#6B6A64]">
            <span className="font-semibold text-[#141413]">
              {selectedTestIds.length}
            </span>{" "}
            of {catalog?.length ?? 0} tests selected
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={selectedTestIds.length === 0 || isReviewPending}
              onClick={handleBulkApprove}
            >
              Approve selected ({selectedTestIds.length})
            </Button>

            <Button
              variant="primary"
              size="sm"
              disabled={isReviewPending}
              onClick={handleApproveAllAndRun}
              className="gap-1.5"
            >
              <span>Approve all and run</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* EDIT TEST DRAWER */}
      <Drawer
        isOpen={Boolean(editingTest)}
        onClose={() => setEditingTest(null)}
        title="Edit Catalog Test"
        subtitle={`ID: ${editingTest?.id || ""}`}
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditingTest(null)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSaveEdit}
              isLoading={isUpdatePending}
            >
              Save Changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-[#141413]">
              Test Title
            </label>
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg font-medium text-[#141413]"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-[#141413]">
              Priority
            </label>
            <select
              value={editPriority}
              onChange={(e) => setEditPriority(e.target.value as TestPriority)}
              className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413]"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-[#141413]">
              Expected Result
            </label>
            <textarea
              rows={3}
              value={editExpected}
              onChange={(e) => setEditExpected(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413]"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-[#141413]">
              Test Steps (One per line)
            </label>
            <textarea
              rows={6}
              value={editStepsText}
              onChange={(e) => setEditStepsText(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg font-mono text-[#141413]"
            />
          </div>
        </div>
      </Drawer>

      {/* REJECT WITH REASON DIALOG */}
      <Dialog
        open={Boolean(rejectingTest)}
        onOpenChange={(open) => !open && setRejectingTest(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Test</DialogTitle>
            <DialogDescription>
              Provide a reason for rejecting &quot;{rejectingTest?.title}&quot;.
              This will be permanently recorded in the Review Log.
            </DialogDescription>
          </DialogHeader>

          <div className="py-2">
            <textarea
              rows={3}
              placeholder="e.g. This flow is deprecated or covered by smoke test 4..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="w-full p-3 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] focus:outline-none focus:ring-2 focus:ring-[#D97757]"
            />
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRejectingTest(null)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleConfirmReject}
              isLoading={isReviewPending}
            >
              Confirm Rejection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* REVIEW LOG DRAWER */}
      <Drawer
        isOpen={isLogDrawerOpen}
        onClose={() => setIsLogDrawerOpen(false)}
        title="Review Decision Audit Log"
        subtitle="Immutable ledger of human and Reviewer agent decisions"
      >
        <div className="space-y-3">
          {!reviewLog || reviewLog.length === 0 ? (
            <p className="text-xs text-[#8A887F] italic text-center py-8">
              No review decisions logged yet.
            </p>
          ) : (
            reviewLog.map((log, idx) => (
              <div
                key={idx}
                className="p-3 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] space-y-1.5"
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 font-medium">
                    {log.actor === "reviewer_agent" ? (
                      <span className="flex items-center gap-1 text-[#D97757]">
                        <Bot className="w-3.5 h-3.5" />
                        <span>Reviewer Agent</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[#141413]">
                        <User className="w-3.5 h-3.5 text-[#6B6A64]" />
                        <span>Human Reviewer</span>
                      </span>
                    )}
                  </div>

                  <Chip variant={log.decision} size="xs">
                    {log.decision}
                  </Chip>
                </div>

                <p className="text-xs text-[#141413] font-mono">
                  Test: {log.test_id}
                </p>

                {log.reason && (
                  <p className="text-xs text-[#6B6A64] bg-white p-2 rounded-lg border border-[#E3DACC]/60">
                    &ldquo;{log.reason}&rdquo;
                  </p>
                )}

                <p className="text-[10px] text-[#8A887F] font-mono text-right">
                  {formatRelativeTime(log.at)}
                </p>
              </div>
            ))
          )}
        </div>
      </Drawer>
    </div>
  );
}

// Collapsible App Map Node Component
function AppMapTreeNode({ node }: { node: AppMapNode }) {
  const [isOpen, setIsOpen] = useState(true);
  const hasChildren = node.children && node.children.length > 0;

  return (
    <div className="space-y-2 border-l border-[#E3DACC] pl-4 my-2">
      <div className="flex items-start gap-2 group">
        {hasChildren && (
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="text-[#8A887F] hover:text-[#141413] mt-0.5 cursor-pointer"
          >
            {isOpen ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
          </button>
        )}

        <div className="flex-1 bg-[#FAF9F5] p-3 rounded-xl border border-[#E3DACC] space-y-1.5 hover:bg-white transition-colors">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-[#141413]">
              {node.url}
            </span>
            {node.status_code && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#EBF2EB] text-[#47704A] border border-[#D2E3D3]">
                HTTP {node.status_code}
              </span>
            )}
          </div>

          {node.title && (
            <p className="text-xs text-[#6B6A64] font-medium">{node.title}</p>
          )}

          {node.actions_found && node.actions_found.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {node.actions_found.map((action, i) => (
                <span
                  key={i}
                  className="text-[10px] font-mono bg-white px-1.5 py-0.5 rounded border border-[#E3DACC] text-[#6B6A64]"
                >
                  {action}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {hasChildren && isOpen && (
        <div className="space-y-2">
          {node.children!.map((child) => (
            <AppMapTreeNode key={child.id} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}
