-- Visual QA helper for the six AI Video Creator Fusion Titles.
-- It is intentionally locked to the disposable validation project so it can
-- never modify a production timeline by accident.

local EXPECTED_PROJECT = "AIVC Transparency QA"
local EXPECTED_TIMELINE = "AIVC Alpha QA 1080x1920"

local project_manager = resolve:GetProjectManager()
local project = project_manager and project_manager:GetCurrentProject()
if not project or project:GetName() ~= EXPECTED_PROJECT then
    print("AIVC_QA_ABORT unexpected project")
    return
end

local timeline = project:GetCurrentTimeline()
if not timeline or timeline:GetName() ~= EXPECTED_TIMELINE then
    print("AIVC_QA_ABORT unexpected timeline")
    return
end

local width = tostring(timeline:GetSetting("timelineResolutionWidth"))
local height = tostring(timeline:GetSetting("timelineResolutionHeight"))
if width ~= "1080" or height ~= "1920" then
    print("AIVC_QA_ABORT unexpected resolution", width, height)
    return
end

local inserts = {
    { "01:00:02:00", "AI VC - Dual Mechanism" },
    { "01:00:07:00", "AI VC - Headline" },
    { "01:00:12:00", "AI VC - Biological Effects" },
    { "01:00:17:00", "AI VC - Big Number Oral" },
    { "01:00:22:00", "AI VC - Big Number Injectable" },
    { "01:00:27:00", "AI VC - Clinical Status" },
}

resolve:OpenPage("edit")
if timeline:GetTrackCount("video") < 2 then
    timeline:AddTrack("video")
end
timeline:SetTrackName("video", 2, "AIVC Inserts QA")
timeline:SetTrackLock("video", 1, true)

local inserted = 0
for _, entry in ipairs(inserts) do
    timeline:SetCurrentTimecode(entry[1])
    local item = timeline:InsertFusionTitleIntoTimeline(entry[2])
    if item then
        item:SetName("QA - " .. entry[2])
        item:SetClipColor("Teal")
        inserted = inserted + 1
        print("AIVC_QA_INSERT", entry[2], entry[1], item:GetStart(), item:GetEnd())
    else
        print("AIVC_QA_FAILED", entry[2], entry[1])
    end
end

timeline:SetTrackLock("video", 1, false)
timeline:SetCurrentTimecode("01:00:03:00")
project_manager:SaveProject()
print("AIVC_QA_DONE", inserted, width, height)
