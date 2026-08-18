-- Visual QA helper for the three transparent overlay designs added after the
-- original six inserts. It can only change the disposable QA project.

local EXPECTED_PROJECT = "AIVC Transparency QA"
local EXPECTED_TIMELINE = "AIVC Alpha QA 1080x1920"

local project_manager = resolve:GetProjectManager()
local project = project_manager and project_manager:GetCurrentProject()
if not project or project:GetName() ~= EXPECTED_PROJECT then
    print("AIVC_DESIGN_QA_ABORT unexpected project")
    return
end

local timeline = project:GetCurrentTimeline()
if not timeline or timeline:GetName() ~= EXPECTED_TIMELINE then
    print("AIVC_DESIGN_QA_ABORT unexpected timeline")
    return
end

local width = tostring(timeline:GetSetting("timelineResolutionWidth"))
local height = tostring(timeline:GetSetting("timelineResolutionHeight"))
if width ~= "1080" or height ~= "1920" then
    print("AIVC_DESIGN_QA_ABORT unexpected resolution", width, height)
    return
end

local inserts = {
    { "01:00:02:00", "AI VC - Newspaper Sidebar" },
    { "01:00:07:00", "AI VC - Kinetic Text" },
    { "01:00:17:00", "AI VC - 5 Info Lines" },
}

resolve:OpenPage("edit")
while timeline:GetTrackCount("video") < 3 do
    timeline:AddTrack("video")
end
timeline:SetTrackName("video", 3, "AIVC Design QA")
timeline:SetTrackLock("video", 1, true)
timeline:SetTrackEnable("video", 2, false)

local inserted = 0
for _, entry in ipairs(inserts) do
    timeline:SetCurrentTimecode(entry[1])
    local item = timeline:InsertFusionTitleIntoTimeline(entry[2])
    if item then
        item:SetName("QA - " .. entry[2])
        item:SetClipColor("Teal")
        inserted = inserted + 1
        print("AIVC_DESIGN_QA_INSERT", entry[2], entry[1], item:GetStart(), item:GetEnd())
    else
        print("AIVC_DESIGN_QA_FAILED", entry[2], entry[1])
    end
end

timeline:SetTrackLock("video", 1, false)
timeline:SetCurrentTimecode("01:00:03:00")
project_manager:SaveProject()
print("AIVC_DESIGN_QA_DONE", inserted, width, height)
