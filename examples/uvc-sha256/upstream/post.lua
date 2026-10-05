-- post.lua
-- Reads the payload file into a variable
local file = io.open("payload.dat", "r")
if not file then
    print("Error: payload.dat not found!")
    return
end
wrk.body = file:read("*a")
file:close()

-- Sets the request method and headers
wrk.method = "POST"
wrk.headers["Content-Type"] = "text/plain"
