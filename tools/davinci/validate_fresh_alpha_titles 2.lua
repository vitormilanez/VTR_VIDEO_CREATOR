-- Builds a clean, disposable V1 + V2 timeline to verify title alpha without
-- relying on any titles inserted before the current package was installed.

local EXPECTED_PROJECT = "AIVC Transparency QA"
local QA_TIMELINE = "AIVC Fresh Alpha QA v2 1080x1920"

local project_manager = resolve:GetProjectManager()
local project = project_manager and project_manager:GetCurrentProject()
if not project or project:GetName() ~= EXPECTED_PROJECT then
    print("AIVC_FRESH_QA_ABORT unexpected project")
    return
end

local source_timeline = project:GetCurrentTimeline()
if not source_timeline then
    print("AIVC_FRESH_QA_ABORT no source timeline")
    return
end

local source_items = source_timeline:GetItemListInTrack("video", 1)
if not source_items or #source_items == 0 then
    print("AIVC_FRESH_QA_ABORT no V1 source clip")
    return
end

local source_media = source_items[1]:GetMediaPoolItem()
if not source_media then
    print("AIVC_FRESH_QA_ABORT source has no media pool item")
    return
end

local media_pool = project:GetMediaPool()
local qa_timeline = media_pool:CreateEmptyTimeline(QA_TIMELINE)
if not qa_timeline then
    print("AIVC_FRESH_QA_ABORT timeline name already exists or could not be created")
    return
end

project:SetCurrentTimeline(qa_timeline)
qa_timeline:SetStartTimecode("01:00:00:00")
qa_timeline:SetSetting("timelineResolutionWidth", "1080")
qa_timeline:SetSetting("timelineResolutionHeight", "1920")
media_pool:AppendToTimeline({{
    mediaPoolItem = source_media,
    mediaType = 1,
    trackIndex = 1,
    recordFrame = qa_timeline:GetStartFrame(),
}})
qa_timeline:AddTrack("video")
print("AIVC_FRESH_QA_TRACKS", qa_timeline:GetTrackCount("video"))
qa_timeline:SetTrackName("video", 2, "AIVC Fresh Titles QA")
qa_timeline:SetTrackLock("video", 1, true)

local inserts = {
    { "01:00:02:00", "AI VC - Newspaper Sidebar" },
    { "01:00:07:00", "AI VC - Kinetic Text" },
    { "01:00:12:00", "AI VC - 5 Info Lines" },
}

local inserted = 0
for _, entry in ipairs(inserts) do
    qa_timeline:SetCurrentTimecode(entry[1])
    local item = qa_timeline:InsertFusionTitleIntoTimeline(entry[2])
    if item then
        item:SetName("Fresh QA - " .. entry[2])
        item:SetClipColor("Teal")
        inserted = inserted + 1
        print("AIVC_FRESH_QA_INSERT", entry[2], item:GetStart(), item:GetEnd())
    else
        print("AIVC_FRESH_QA_FAILED", entry[2])
    end
end

qa_timeline:SetTrackLock("video", 1, false)
qa_timeline:SetCurrentTimecode("01:00:03:00")
resolve:OpenPage("edit")
project_manager:SaveProject()
print("AIVC_FRESH_QA_DONE", inserted, qa_timeline:GetTrackCount("video"))
